-- Harness: the controller's helper library for Civilization VI, run in the game's InGame Lua
-- state through the FireTuner relay (docs/design/2026-09-26-civ6-governor-design.md, ruling 2).
--
-- The controller prepends `local HARNESS_VERSION = "<hash of this file>"` and sends the whole
-- file; a second install of the same version is a no-op. Every public function prints exactly
-- one JSON line ({"ok": true, ...} or {"ok": false, "error": "..."}), since the tuner returns
-- output only through print(). The controller calls functions with arguments it encodes itself
-- (JSON-style string literals of corpus type keys, numbers); nothing here evaluates text.
--
-- API names for purchases (CityCommandTypes.PURCHASE, GetGold():GetPurchaseCost), production
-- (CityOperationTypes.BUILD with VALUE_EXCLUSIVE), research and civics (GameCore's
-- SetResearchingTech / SetProgressingCivic), policies (UNLOCK_POLICIES, then
-- RequestPolicyChanges; slot types 0 economic, 1 military, 2 diplomatic, 3 wildcard), the build
-- queue's current item (GetCurrentProductionTypeHash), era score (Game.GetEras()) and military
-- strength (GetStats():GetMilitaryStrength()) are ported from civ6-mcp
-- (https://github.com/lmwilki/civ6-mcp), MIT License, Copyright (c) 2026 Liam Wilkinson.
-- Checked live on 1.0.12.68 (games/civ6-kublai/journal.md). The snapshot's defence, religion and
-- blocker fields follow docs/design/2026-09-27-civ6-levers-design.md, ruling 11; each is left out
-- when the game's API fails for it.

if Harness and Harness.version == HARNESS_VERSION then
  return
end

Harness = { version = HARNESS_VERSION }
local H = Harness

-- ---- JSON --------------------------------------------------------------------------------------

local ARRAY = {}                      -- metatable marking a table as a JSON array (even when empty)
function H.array(t)
  return setmetatable(t or {}, ARRAY)
end

-- A field that is present with no value (a Lua table cannot hold nil): encoded as JSON null.
local NULL = setmetatable({}, { __tostring = function() return 'null' end })
H.null = NULL

local ESC = { ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }

local function enc_string(s)
  return '"' .. s:gsub('[%c"\\]', function(c)
    return ESC[c] or string.format('\\u%04x', c:byte())
  end) .. '"'
end

local function is_array(t)
  if getmetatable(t) == ARRAY then return true end
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  if n == 0 then return false end
  for i = 1, n do
    if t[i] == nil then return false end
  end
  return true
end

local encode
encode = function(v, depth)
  depth = depth or 0
  if depth > 20 then error('json: nested too deep') end
  local t = type(v)
  if v == nil or v == NULL then return 'null' end
  if t == 'boolean' then return v and 'true' or 'false' end
  if t == 'number' then
    if v ~= v or v == math.huge or v == -math.huge then return 'null' end
    if v == math.floor(v) and math.abs(v) < 1e15 then return string.format('%d', v) end
    return string.format('%.14g', v)          -- full precision (a treasury over 10,000 stays exact)
  end
  if t == 'string' then return enc_string(v) end
  if t == 'table' then
    local out = {}
    if is_array(v) then
      for i = 1, #v do out[i] = encode(v[i], depth + 1) end
      return '[' .. table.concat(out, ',') .. ']'
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = tostring(k) end
    table.sort(keys)
    for _, k in ipairs(keys) do
      local val = v[k]
      if val == nil then val = v[tonumber(k)] end
      out[#out + 1] = enc_string(k) .. ':' .. encode(val, depth + 1)
    end
    return '{' .. table.concat(out, ',') .. '}'
  end
  return enc_string(tostring(v))
end
H.encode = encode

-- Run `fn`, print its table as one JSON line; an error becomes {"ok": false, "error": ...}.
function H.run(fn, ...)
  local ok, res = pcall(fn, ...)
  if not ok then
    res = { ok = false, error = tostring(res) }
  elseif type(res) ~= 'table' then
    res = { ok = true, result = res }
  elseif res.ok == nil then
    res.ok = true
  end
  print(encode(res))
end

local function fail(msg)
  return { ok = false, error = msg }
end

-- ---- lookups -----------------------------------------------------------------------------------

function H.me()
  local me = Game.GetLocalPlayer()
  if me == nil or me < 0 then me = AutoplayManager.GetReturnAsPlayer() end
  return me
end

local function name_of(loc)
  if loc == nil then return nil end
  local ok, s = pcall(Locale.Lookup, loc)
  return ok and s or tostring(loc)
end

local HASH
local function type_of_hash(h)
  if HASH == nil then
    HASH = {}
    for _, tbl in ipairs({ 'Units', 'Buildings', 'Districts', 'Projects' }) do
      for row in GameInfo[tbl]() do
        local key = row.UnitType or row.BuildingType or row.DistrictType or row.ProjectType
        HASH[row.Hash] = key
      end
    end
  end
  return HASH[h]
end

-- (table, row) for a type key: UNIT_*, BUILDING_*, DISTRICT_*, PROJECT_*.
local function item_row(key)
  for _, tbl in ipairs({ 'Units', 'Buildings', 'Districts', 'Projects' }) do
    local row = GameInfo[tbl][key]
    if row then return tbl, row end
  end
  return nil, nil
end

-- Our city by its ID (number) or its name as shown (any case).
function H.find_city(ref)
  local me = H.me()
  local want = type(ref) == 'string' and ref:lower() or nil
  for _, c in Players[me]:GetCities():Members() do
    if c:GetID() == ref or (want and (name_of(c:GetName()) or ''):lower() == want) then
      return c
    end
  end
  return nil
end

local function at_war_with(me, other)
  local ok, war = pcall(function() return Players[me]:GetDiplomacy():IsAtWarWith(other) end)
  return ok and war or false
end

-- The purchase command's parameters for a unit or building in a city and its live price, or why it
-- cannot be bought.
local function purchase_params(c, key, currency)
  local tbl, row = item_row(key)
  if row == nil then return nil, 'unknown item ' .. tostring(key) end
  if tbl ~= 'Units' and tbl ~= 'Buildings' then return nil, key .. ' cannot be bought (units and buildings only)' end
  local y = GameInfo.Yields[currency == 'faith' and 'YIELD_FAITH' or 'YIELD_GOLD']
  local params = {}
  params[CityCommandTypes[tbl == 'Units' and 'PARAM_UNIT_TYPE' or 'PARAM_BUILDING_TYPE']] = row.Hash
  params[CityCommandTypes.PARAM_YIELD_TYPE] = y.Index
  local formation = -1
  if tbl == 'Units' then
    formation = MilitaryFormationTypes.STANDARD_MILITARY_FORMATION
    params[CityCommandTypes.PARAM_MILITARY_FORMATION_TYPE] = formation
  end
  local cost = c:GetGold():GetPurchaseCost(y.Index, row.Hash, formation)
  return params, nil, cost
end

-- Whether the game allows a purchase now: the balance, a unit already on the city tile (stacking),
-- and the faith rules are the game's own check.
local function purchase_allowed(c, params)
  return CityManager.CanStartCommand(c, CityCommandTypes.PURCHASE, false, params, false) and true or false
end

-- The city's City Center district: its garrison and walls, and its defence strength.
local function center_of(c)
  for _, d in c:GetDistricts():Members() do
    local row = GameInfo.Districts[d:GetType()]
    if row and row.DistrictType == 'DISTRICT_CITY_CENTER' then return d end
  end
  return nil
end

local function is_military(row)
  return row ~= nil and row.FormationClass ~= 'FORMATION_CLASS_CIVILIAN' and row.FormationClass ~= 'FORMATION_CLASS_SUPPORT'
end

-- A unit's kind for defence: siege, cavalry (light or heavy), ranged, or melee. Melee includes
-- anti-cavalry (the Spearman) and recon; melee and cavalry are the kinds that can capture a city.
local CAVALRY = { PROMOTION_CLASS_LIGHT_CAVALRY = true, PROMOTION_CLASS_HEAVY_CAVALRY = true }
local function unit_kind(row)
  if row.PromotionClass == 'PROMOTION_CLASS_SIEGE' then return 'siege' end
  if CAVALRY[row.PromotionClass] then return 'cavalry' end
  if (row.RangedCombat or 0) > 0 or (row.Bombard or 0) > 0 then return 'ranged' end
  return 'melee'
end

-- Land units that defend a city (pillars.toml [actions.purchase] defender_classes, as promotion classes).
local DEFENDER = { PROMOTION_CLASS_MELEE = true, PROMOTION_CLASS_RANGED = true, PROMOTION_CLASS_ANTI_CAVALRY = true,
                   PROMOTION_CLASS_LIGHT_CAVALRY = true, PROMOTION_CLASS_HEAVY_CAVALRY = true }

-- Enemy military units (at war with us, or barbarians) within 3 tiles of the city, with their
-- distance, and whether its City Center is under siege or damaged.
local function threat(me, c)
  local hostile = {}
  local cx, cy = c:GetX(), c:GetY()
  for dy = -3, 3 do
    for dx = -3, 3 do
      local x, y = cx + dx, cy + dy
      local dist = Map.GetPlotDistance(cx, cy, x, y)
      if dist <= 3 then
        local units = Map.GetUnitsAt(x, y)
        if units then
          for u in units:Units() do
            local owner = u:GetOwner()
            local row = GameInfo.Units[u:GetType()]
            if owner ~= me and is_military(row) and (Players[owner]:IsBarbarian() or at_war_with(me, owner)) then
              hostile[#hostile + 1] = { u = u, row = row, x = x, y = y, dist = dist }
            end
          end
        end
      end
    end
  end
  local siege, damaged = false, false
  local d = center_of(c)
  if d then
    pcall(function() siege = d:IsUnderSiege() end)
    pcall(function() damaged = (d:GetDamage(DefenseTypes.DISTRICT_GARRISON) or 0) > 0 end)
  end
  return hostile, siege, damaged
end

-- Our land combat unit on the city tile (its garrison), or null.
local function garrison_of(me, c)
  local units = Map.GetUnitsAt(c:GetX(), c:GetY())
  if units then
    for u in units:Units() do
      local row = GameInfo.Units[u:GetType()]
      if u:GetOwner() == me and row and row.FormationClass == 'FORMATION_CLASS_LAND_COMBAT' then return row.UnitType end
    end
  end
  return NULL
end

local function defense_of(d)
  local g_max = d:GetMaxDamage(DefenseTypes.DISTRICT_GARRISON) or 0
  local w_max = d:GetMaxDamage(DefenseTypes.DISTRICT_OUTER) or 0
  return { garrison_hp = g_max - (d:GetDamage(DefenseTypes.DISTRICT_GARRISON) or 0), garrison_max = g_max,
           walls_hp = w_max - (d:GetDamage(DefenseTypes.DISTRICT_OUTER) or 0), walls_max = w_max }
end

-- Damage formula (GlobalParameters COMBAT_BASE_DAMAGE 24; e^(difference / 25)), the fallback when
-- the game's own combat preview gives no answer.
local BASE_DAMAGE, DAMAGE_PER_STRENGTH = 24, 0.04

-- One attack of an enemy unit on the City Center: the game's combat preview (as UnitPanel.lua
-- uses it), else the formula with the unit's strength against the district's defence strength.
-- A preview of 0 is no answer (seen live at T129: an enemy Catapult 4 tiles from Xi'an previewed
-- 0 damage; any real attack does some).
local function attack_damage(e, kind, d, busy)
  local ctype, strength = nil, e.u:GetCombat()
  if kind == 'ranged' or kind == 'siege' then
    ctype, strength = CombatTypes.RANGED, e.u:GetRangedCombat()
    if e.u:GetBombardCombat() > strength then
      ctype, strength = CombatTypes.BOMBARD or CombatTypes.RANGED, e.u:GetBombardCombat()
    end
  end
  if not busy then
    local ok, r = pcall(CombatManager.SimulateAttackVersus, e.u:GetComponentID(), d:GetComponentID(), ctype)
    if ok and type(r) == 'table' then
      local D = r[CombatResultParameters.DEFENDER]
      local dmg = type(D) == 'table' and D[CombatResultParameters.DAMAGE_TO] or nil
      if type(dmg) == 'number' and dmg > 0 then return dmg, 'simulated' end
    end
  end
  local ok, def = pcall(function() return d:GetDefenseStrength() end)
  if ok and type(def) == 'number' and strength > 0 then
    return BASE_DAMAGE * math.exp(DAMAGE_PER_STRENGTH * (strength - def)), 'formula'
  end
  return nil, nil
end

local LIST_CAP = 8               -- enemies and defenders listed per threatened city

local function by_distance(a, b)
  if a.dist ~= b.dist then return a.dist < b.dist end
  return a.hp < b.hp
end

local function capped(list)
  table.sort(list, by_distance)
  local out = H.array()
  for i = 1, math.min(LIST_CAP, #list) do out[i] = list[i] end
  return out
end

-- The two cheapest defenders the city can build, with their live gold and faith prices and whether
-- the game allows each purchase now.
local function defence_prices(c)
  local bq = c:GetBuildQueue()
  local out = {}
  for row in GameInfo.Units() do
    if DEFENDER[row.PromotionClass] and row.Domain == 'DOMAIN_LAND' and bq:CanProduce(row.Hash, true) then
      local e = { unit = row.UnitType }
      for _, currency in ipairs({ 'gold', 'faith' }) do
        local params, _, cost = purchase_params(c, row.UnitType, currency)
        if params then
          e[currency] = cost
          e[currency .. '_allowed'] = purchase_allowed(c, params)
        end
      end
      out[#out + 1] = e
    end
  end
  table.sort(out, function(a, b) return (a.gold or math.huge) < (b.gold or math.huge) end)
  local top = H.array()
  for i = 1, math.min(2, #out) do top[i] = out[i] end
  return top
end

-- For a threatened city: the enemies near it, our units near it, what can capture it, the damage
-- one attack from each enemy in range would do, whether it can strike, and what a defender costs.
-- Each part is left out when the game's API fails for it.
local function danger_detail(me, c, info, hostile)
  local d = center_of(c)
  local busy = false
  pcall(function() busy = UI.IsGameCoreBusy() end)
  pcall(function()
    local enemies, capture, incoming, from = {}, 0, 0, nil
    for _, e in ipairs(hostile) do
      local kind = unit_kind(e.row)
      local hp = e.u:GetMaxDamage() - e.u:GetDamage()
      enemies[#enemies + 1] = { id = e.u:GetID(), owner = e.u:GetOwner(), type = e.row.UnitType, kind = kind,
                                x = e.x, y = e.y, dist = e.dist, hp = hp }
      if e.dist == 1 and (kind == 'melee' or kind == 'cavalry') then capture = capture + 1 end
      local reach = 1
      if kind == 'ranged' or kind == 'siege' then pcall(function() reach = e.u:GetRange() end) end
      if d and e.dist >= 1 and e.dist <= reach then
        local dmg, src = attack_damage(e, kind, d, busy)
        if dmg then
          incoming = incoming + dmg
          from = (from == nil or from == src) and src or 'mixed'
        end
      end
    end
    info.enemies = capped(enemies)
    info.capture_adjacent = capture
    info.incoming = math.floor(incoming + 0.5)
    info.incoming_from = from
  end)
  pcall(function()
    local cx, cy = c:GetX(), c:GetY()
    local ours = {}
    for _, u in Players[me]:GetUnits():Members() do
      local row = GameInfo.Units[u:GetType()]
      if is_military(row) and u:GetX() >= 0 then
        local dist = Map.GetPlotDistance(cx, cy, u:GetX(), u:GetY())
        if dist <= 3 then
          ours[#ours + 1] = { id = u:GetID(), type = row.UnitType, kind = unit_kind(row), x = u:GetX(), y = u:GetY(),
                              dist = dist, hp = u:GetMaxDamage() - u:GetDamage(), moves = u:GetMovesRemaining(),
                              attacks = u:GetAttacksRemaining(), range = u:GetRange() }
        end
      end
    end
    info.defenders = capped(ours)
  end)
  pcall(function()
    local res = CityManager.GetCommandTargets(c, CityCommandTypes.RANGE_ATTACK)
    local n = 0
    for _, m in ipairs((res or {})[CityCommandResults.MODIFIERS] or {}) do
      if m == CityCommandResults.MODIFIER_IS_TARGET then n = n + 1 end
    end
    info.can_strike = n > 0
  end)
  local ok, prices = pcall(defence_prices, c)
  if ok then info.defence_prices = prices end
end

-- ---- snapshot ----------------------------------------------------------------------------------

local SLOT_NAMES = { [0] = 'economic', [1] = 'military', [2] = 'diplomatic', [3] = 'wildcard', [4] = 'great_person' }

local function city_info(me, c)
  local bq = c:GetBuildQueue()
  local producing, turns = nil, nil
  if bq:GetSize() > 0 then
    producing = type_of_hash(bq:GetCurrentProductionTypeHash())
    turns = bq:GetTurnsLeft()
  end
  local districts, wonders, buildings = H.array(), H.array(), H.array()
  for _, d in c:GetDistricts():Members() do
    local row = GameInfo.Districts[d:GetType()]
    if row and row.DistrictType ~= 'DISTRICT_CITY_CENTER' then
      districts[#districts + 1] = row.DistrictType .. (d:IsComplete() and '' or ' (building)')
    end
  end
  local b = c:GetBuildings()
  for row in GameInfo.Buildings() do
    if b:HasBuilding(row.Index) then
      buildings[#buildings + 1] = row.BuildingType
      if row.IsWonder then wonders[#wonders + 1] = row.BuildingType end
    end
  end
  local hostile, siege, damaged = threat(me, c)
  local loyalty = nil
  pcall(function() loyalty = math.floor(c:GetCulturalIdentity():GetLoyalty()) end)
  local info = {
    id = c:GetID(), name = name_of(c:GetName()), pop = c:GetPopulation(), capital = c:IsCapital(),
    x = c:GetX(), y = c:GetY(),
    producing = producing, turns_left = turns, districts = districts, wonders = wonders, buildings = buildings,
    food = c:GetYield(YieldTypes.FOOD), production = c:GetYield(YieldTypes.PRODUCTION),
    enemies_near = #hostile, under_siege = siege, damaged = damaged,
    threatened = #hostile > 0 or siege or damaged, loyalty = loyalty,
  }
  pcall(function() info.garrison = garrison_of(me, c) end)
  pcall(function()
    local d = center_of(c)
    if d then info.defense = defense_of(d) end
  end)
  if info.threatened then danger_detail(me, c, info, hostile) end
  return info
end

local function majors(me)
  local out = H.array()
  local diplo = Players[me]:GetDiplomacy()
  for i = 0, 62 do
    local p = Players[i]
    if i ~= me and p and p:IsAlive() and p:IsMajor() and diplo:HasMet(i) then
      local cfg = PlayerConfigurations[i]
      local cities = 0
      for _ in p:GetCities():Members() do cities = cities + 1 end
      out[#out + 1] = {
        id = i, civ = cfg:GetCivilizationTypeName(), leader = cfg:GetLeaderTypeName(),
        score = p:GetScore(), military = p:GetStats():GetMilitaryStrength(), cities = cities,
        techs = p:GetStats():GetNumTechsResearched(), civics = p:GetStats():GetNumCivicsCompleted(),
        at_war = at_war_with(me, i),
      }
    end
  end
  return out
end

local function wonders_elsewhere(me)
  local rows = {}
  for row in GameInfo.Buildings() do
    if row.IsWonder then rows[#rows + 1] = row end
  end
  local out, seen = H.array(), {}
  for i = 0, 63 do
    local p = Players[i]
    if i ~= me and p and p:IsAlive() then
      for _, c in p:GetCities():Members() do
        local b = c:GetBuildings()
        for _, row in ipairs(rows) do
          if not seen[row.BuildingType] and b:HasBuilding(row.Index) then
            seen[row.BuildingType] = true
            out[#out + 1] = row.BuildingType
          end
        end
      end
    end
  end
  return out
end

local function blocker(me)
  local b = NotificationManager.GetFirstEndTurnBlocking(me)
  if b == nil or b == EndTurnBlockingTypes.NO_ENDTURN_BLOCKING then return nil end
  for k, v in pairs(EndTurnBlockingTypes) do
    if v == b then return k end
  end
  return tostring(b)
end

-- Every end-turn blocker, not only the first (the first is `blocker`).
local function blockers_all(me)
  local out = H.array()
  for _, b in ipairs(NotificationManager.GetAllEndTurnBlocking(me) or {}) do
    local name = tostring(b)
    for k, v in pairs(EndTurnBlockingTypes) do
      if v == b then name = k end
    end
    out[#out + 1] = name
  end
  return out
end

-- Pantheon, religion and the Great Prophet race (ReligionScreen.lua: GetPantheon,
-- CanCreatePantheon, GetReligionTypeCreated, GetMinimumFaithNextPantheon; the religions a map
-- allows are the Prophets it has, Map_GreatPersonClasses).
local function religion_info(me)
  local pr, gr = Players[me]:GetReligion(), Game.GetReligion()
  local pan, rel = pr:GetPantheon(), pr:GetReligionTypeCreated()
  local founded = 0
  for _, r in ipairs(gr:GetReligions() or {}) do
    local row = GameInfo.Religions[r.Religion]
    if row and not row.Pantheon and gr:HasBeenFounded(r.Religion) then founded = founded + 1 end
  end
  local max = nil
  local size = GameInfo.Maps[Map.GetMapSize()]
  if size then
    for row in GameInfo.Map_GreatPersonClasses() do
      if row.MapSizeType == size.MapSizeType and row.GreatPersonClassType == 'GREAT_PERSON_CLASS_PROPHET' then
        max = row.MaxWorldInstances
      end
    end
  end
  local points, cost = nil, nil
  local prophet = GameInfo.GreatPersonClasses['GREAT_PERSON_CLASS_PROPHET']
  if prophet then
    pcall(function() points = math.floor(Players[me]:GetGreatPeoplePoints():GetPointsTotal(prophet.Index)) end)
    pcall(function()
      for _, e in ipairs(Game.GetGreatPeople():GetTimeline() or {}) do
        -- the largest integer (seen live at T124, 4 of 4 religions founded): no Prophet is left
        if e.Class == prophet.Index and e.Cost < 2147483647 then cost = e.Cost end
      end
    end)
  end
  local belief = pan ~= nil and pan >= 0 and GameInfo.Beliefs[pan] or nil
  local religion = rel ~= nil and rel >= 0 and GameInfo.Religions[rel] or nil
  return {
    pantheon = belief and belief.BeliefType or NULL, can_create_pantheon = pr:CanCreatePantheon() and true or false,
    pantheon_cost = gr:GetMinimumFaithNextPantheon(),
    religion = religion and religion.ReligionType or NULL, religions_founded = founded, religions_max = max,
    prophet_points = points, prophet_cost = cost,
  }
end

local function great_people(me)
  local gp = Game.GetGreatPeople()
  local points = Players[me]:GetGreatPeoplePoints()
  local current = H.array()
  for _, e in ipairs(gp:GetTimeline() or {}) do
    local class = GameInfo.GreatPersonClasses[e.Class]
    current[#current + 1] = {
      class = class and class.GreatPersonClassType, cost = e.Cost,
      ours = math.floor(points:GetPointsTotal(e.Class)),
    }
  end
  local past = H.array()
  local list = gp:GetPastTimeline() or {}
  for i = math.max(1, #list - 4), #list do
    local e = list[i]
    local class = GameInfo.GreatPersonClasses[e.Class]
    past[#past + 1] = { class = class and class.GreatPersonClassType, claimant = e.Claimant, turn = e.TurnGranted }
  end
  return { current = current, past = past, recruited = #list }
end

-- What orders can name now: techs and civics we can start, unlocked policies not slotted, and per
-- city what it can produce (units, buildings and projects; districts only once placed).
local function options(me, p)
  local techs, civics, policies = H.array(), H.array(), H.array()
  local t, cu = p:GetTechs(), p:GetCulture()
  for row in GameInfo.Technologies() do
    if not t:HasTech(row.Index) and t:CanResearch(row.Index) then techs[#techs + 1] = row.TechnologyType end
  end
  for row in GameInfo.Civics() do
    if not cu:HasCivic(row.Index) and cu:CanProgress(row.Index) then civics[#civics + 1] = row.CivicType end
  end
  for row in GameInfo.Policies() do
    if cu:IsPolicyUnlocked(row.Index) and not cu:IsPolicyObsolete(row.Index) and not cu:IsPolicyActive(row.Index) then
      policies[#policies + 1] = row.PolicyType
    end
  end
  return { techs = techs, civics = civics, policies = policies }
end

local function can_build(c)
  local bq = c:GetBuildQueue()
  local out = H.array()
  for _, tbl in ipairs({ 'Units', 'Buildings', 'Projects', 'Districts' }) do
    for row in GameInfo[tbl]() do
      local ok = true
      if tbl == 'Buildings' and row.IsWonder then ok = false end
      if tbl == 'Districts' and not bq:HasBeenPlaced(row.Hash) then ok = false end
      if ok and bq:CanProduce(row.Hash, true) then
        out[#out + 1] = row.UnitType or row.BuildingType or row.ProjectType or row.DistrictType
      end
    end
  end
  return out
end

function H.snapshot()
  local me = H.me()
  local p = Players[me]
  local cfg = PlayerConfigurations[me]
  local eras = Game.GetEras()
  local era = GameInfo.Eras[eras:GetCurrentEra()]
  local techs, culture, treasury, religion = p:GetTechs(), p:GetCulture(), p:GetTreasury(), p:GetReligion()

  local cities, food, production = H.array(), 0, 0
  for _, c in p:GetCities():Members() do
    local info = city_info(me, c)
    local ok, list = pcall(can_build, c)
    info.can_build = ok and list or nil
    cities[#cities + 1] = info
    food = food + info.food
    production = production + info.production
  end

  local research = techs:GetResearchingTech()
  local civic = culture:GetProgressingCivic()
  local gov = culture:GetCurrentGovernment()
  local slots = H.array()
  for s = 0, culture:GetNumPolicySlots() - 1 do
    local pol = culture:GetSlotPolicy(s)
    slots[#slots + 1] = {
      slot = s, type = SLOT_NAMES[culture:GetSlotType(s)] or tostring(culture:GetSlotType(s)),
      policy = pol >= 0 and GameInfo.Policies[pol].PolicyType or nil,
    }
  end

  local by_class, by_type, total = {}, {}, 0
  for _, u in p:GetUnits():Members() do
    local row = GameInfo.Units[u:GetType()]
    if row then
      total = total + 1
      local class = (row.FormationClass or 'OTHER'):gsub('^FORMATION_CLASS_', ''):lower()
      by_class[class] = (by_class[class] or 0) + 1
      by_type[row.UnitType] = (by_type[row.UnitType] or 0) + 1
    end
  end

  local known = majors(me)
  local wars = H.array()
  for i = 0, 62 do
    local q = Players[i]
    local free = q and q.IsFreeCities and q:IsFreeCities()
    if i ~= me and q and q:IsAlive() and not q:IsBarbarian() and not free and at_war_with(me, i) then
      wars[#wars + 1] = { id = i, civ = PlayerConfigurations[i]:GetCivilizationTypeName(), major = Players[i]:IsMajor() }
    end
  end

  local seed = MapConfiguration.GetValue('RANDOM_SEED')
  local gp_ok, gp = pcall(great_people, me)
  local opt_ok, opt = pcall(options, me, p)
  local we_ok, we = pcall(wonders_elsewhere, me)
  local rel_ok, rel = pcall(religion_info, me)
  local bl_ok, bl = pcall(blockers_all, me)
  return {
    turn = Game.GetCurrentGameTurn(), player = me,
    civ = cfg:GetCivilizationTypeName(), leader = cfg:GetLeaderTypeName(),
    civ_name = name_of(cfg:GetCivilizationShortDescription()), leader_name = name_of(cfg:GetLeaderName()),
    map_seed = seed and tostring(seed) or nil,
    era = era and era.EraType, era_index = eras:GetCurrentEra(),
    era_score = eras:GetPlayerCurrentScore(me),
    dark_age_threshold = eras:GetPlayerDarkAgeThreshold(me),
    golden_age_threshold = eras:GetPlayerGoldenAgeThreshold(me),
    yields = {
      science = techs:GetScienceYield(), culture = culture:GetCultureYield(),
      faith = religion:GetFaithYield(), gold = treasury:GetGoldYield() - treasury:GetTotalMaintenance(),
      food = food, production = production,
    },
    gold = treasury:GetGoldBalance(), faith = religion:GetFaithBalance(),
    score = p:GetScore(), military = p:GetStats():GetMilitaryStrength(),
    techs_known = p:GetStats():GetNumTechsResearched(), civics_known = p:GetStats():GetNumCivicsCompleted(),
    research = research >= 0 and { tech = GameInfo.Technologies[research].TechnologyType, turns_left = techs:GetTurnsLeft() } or nil,
    civic = civic >= 0 and { civic = GameInfo.Civics[civic].CivicType, turns_left = culture:GetTurnsLeft() } or nil,
    government = gov >= 0 and GameInfo.Governments[gov].GovernmentType or nil,
    policy_slots = slots,
    policies_unlock_cost = culture:GetCostToUnlockPolicies(),
    cities = cities,
    units = { total = total, by_class = by_class, by_type = by_type },
    majors = known, wars = wars,
    great_people = gp_ok and gp or nil,
    wonders_elsewhere = we_ok and we or nil,
    options = opt_ok and opt or nil,
    blocker = blocker(me),
    blockers_all = bl_ok and bl or nil,
    religion = rel_ok and rel or nil,
    autoplay = { active = AutoplayManager.IsActive(), turns = AutoplayManager.GetTurns() },
  }
end

-- ---- orders ------------------------------------------------------------------------------------

-- Research or civic, through the GameCore setters (the UI's request sent from the tuner is
-- ignored, seen live), so these two run only in the GameCore state. The setter changes it at once
-- (checked here) but does not check prerequisites: every one must be known.
local function progress(kind, key)
  local me = H.me()
  local tbl, getter, prereqs, col, pcol = 'Technologies', 'GetTechs', 'TechnologyPrereqs', 'Technology', 'PrereqTech'
  if kind == 'civic' then
    tbl, getter, prereqs, col, pcol = 'Civics', 'GetCulture', 'CivicPrereqs', 'Civic', 'PrereqCivic'
  end
  local row = GameInfo[tbl][key]
  if row == nil then return fail('unknown ' .. kind .. ' ' .. tostring(key)) end
  local holder = Players[me][getter](Players[me])
  local has = function(idx)
    if kind == 'civic' then return holder:HasCivic(idx) end
    return holder:HasTech(idx)
  end
  if has(row.Index) then return fail(key .. ' is already completed') end
  local missing = H.array()
  for pre in GameInfo[prereqs]() do
    if pre[col] == key and not has(GameInfo[tbl][pre[pcol]].Index) then missing[#missing + 1] = pre[pcol] end
  end
  if #missing > 0 then return fail(key .. ' needs ' .. table.concat(missing, ', ') .. ' first') end
  local set = kind == 'civic' and holder.SetProgressingCivic or holder.SetResearchingTech
  if not set then return fail(kind .. ' orders run in the GameCore state only') end
  set(holder, row.Index)
  local now = kind == 'civic' and holder:GetProgressingCivic() or holder:GetResearchingTech()
  if now ~= row.Index then return fail(key .. ' was not taken by the game') end
  return { set = key }
end

function H.set_research(key) return progress('tech', key) end
function H.set_civic(key) return progress('civic', key) end

-- Slot the given policies: each goes to a slot of its own type, else a wildcard slot. Policies
-- already slotted stay where they are; slots holding other policies are cleared for the new ones.
function H.set_policies(keys)
  local me = H.me()
  local culture = Players[me]:GetCulture()
  local n = culture:GetNumPolicySlots()
  if n <= 0 then return fail('no government: no policy slots') end
  local want, rows = {}, {}
  for _, key in ipairs(keys) do
    local row = GameInfo.Policies[key]
    if row == nil then return fail('unknown policy ' .. tostring(key)) end
    if not culture:IsPolicyUnlocked(row.Index) then return fail(key .. ' is not unlocked') end
    want[row.Index] = true
    rows[#rows + 1] = row
  end
  local slot_of = { SLOT_ECONOMIC = 0, SLOT_MILITARY = 1, SLOT_DIPLOMATIC = 2, SLOT_WILDCARD = 3, SLOT_GREAT_PERSON = 4 }
  local taken, placed = {}, {}
  for s = 0, n - 1 do
    local cur = culture:GetSlotPolicy(s)
    if cur >= 0 and want[cur] then
      taken[s] = true
      placed[cur] = true
    end
  end
  local add, clear, assigned = {}, H.array(), {}
  for _, row in ipairs(rows) do
    if not placed[row.Index] then
      local need = slot_of[row.GovernmentSlotType]
      local slot = nil
      for pass = 1, 2 do
        for s = 0, n - 1 do
          local st = culture:GetSlotType(s)
          local fits = (pass == 1 and st == need) or (pass == 2 and st == 3 and need ~= 4)
          if slot == nil and not taken[s] and fits then slot = s end
        end
      end
      if slot == nil then return fail('no free ' .. (SLOT_NAMES[need] or '?') .. ' or wildcard slot for ' .. row.PolicyType) end
      taken[slot] = true
      add[slot] = row.Hash
      clear[#clear + 1] = slot
      assigned[#assigned + 1] = { slot = slot, policy = row.PolicyType }
    end
  end
  if #clear == 0 then return { requested = H.array(), note = 'all already slotted' } end
  local cost = culture:GetCostToUnlockPolicies()
  if cost and cost > 0 then
    return fail('policies are locked until a civic completes (unlocking costs ' .. cost .. ' gold)')
  end
  UI.RequestPlayerOperation(me, PlayerOperations.UNLOCK_POLICIES, {})
  culture:RequestPolicyChanges(clear, add)
  return { requested = assigned }
end

-- Replace the city's production with a unit, building or project (districts only when already
-- placed: placement is not supported yet; wonders need a tile too).
function H.set_production(city_ref, key)
  local c = H.find_city(city_ref)
  if c == nil then return fail('no city of ours named ' .. tostring(city_ref)) end
  local tbl, row = item_row(key)
  if row == nil then return fail('unknown item ' .. tostring(key)) end
  local bq = c:GetBuildQueue()
  if tbl == 'Buildings' and row.IsWonder then return fail(key .. ' is a wonder: placement is not supported yet') end
  if tbl == 'Districts' and not bq:HasBeenPlaced(row.Hash) then
    return fail(key .. ' is a district that has not been placed: placement is not supported yet')
  end
  if not bq:CanProduce(row.Hash, true) then return fail(key .. ' cannot be produced in ' .. name_of(c:GetName())) end
  local param = ({ Units = 'PARAM_UNIT_TYPE', Buildings = 'PARAM_BUILDING_TYPE', Districts = 'PARAM_DISTRICT_TYPE', Projects = 'PARAM_PROJECT_TYPE' })[tbl]
  local params = {}
  params[CityOperationTypes[param]] = row.Hash
  params[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
  CityManager.RequestOperation(c, CityOperationTypes.BUILD, params)
  return { requested = key, city = name_of(c:GetName()), turns = bq:GetTurnsLeft(row.Hash) }
end

-- The live price of an item in a city, and whether the game allows the purchase now.
function H.get_purchase_cost(city_ref, key, currency)
  local c = H.find_city(city_ref)
  if c == nil then return fail('no city of ours named ' .. tostring(city_ref)) end
  local params, err, cost = purchase_params(c, key, currency)
  if params == nil then return fail(err) end
  local me = H.me()
  local balance = currency == 'faith' and Players[me]:GetReligion():GetFaithBalance() or Players[me]:GetTreasury():GetGoldBalance()
  return { item = key, city = name_of(c:GetName()), currency = currency, cost = cost, balance = balance,
           allowed = purchase_allowed(c, params) }
end

-- Buy an item at once. `max_cost` is the most the governor allows (its reserve and treasury
-- share); a higher live price refuses the purchase.
function H.purchase(city_ref, key, currency, max_cost)
  local c = H.find_city(city_ref)
  if c == nil then return fail('no city of ours named ' .. tostring(city_ref)) end
  local params, err, cost = purchase_params(c, key, currency)
  if params == nil then return fail(err) end
  if max_cost ~= nil and cost > max_cost then
    return fail(key .. ' costs ' .. cost .. ' ' .. currency .. ', over the allowed ' .. max_cost)
  end
  local can, results = CityManager.CanStartCommand(c, CityCommandTypes.PURCHASE, false, params, true)
  if not can then
    local why = H.array()
    for _, v in pairs(results or {}) do
      if type(v) == 'table' then
        for _, m in pairs(v) do if type(m) == 'string' then why[#why + 1] = name_of(m) end end
      elseif type(v) == 'string' then
        why[#why + 1] = name_of(v)
      end
    end
    return fail('the game refuses to buy ' .. key .. ' in ' .. name_of(c:GetName()) .. ' for ' .. cost .. ' ' .. currency
      .. (#why > 0 and (': ' .. table.concat(why, '; ')) or ''))
  end
  CityManager.RequestCommand(c, CityCommandTypes.PURCHASE, params)
  return { requested = key, city = name_of(c:GetName()), currency = currency, cost = cost }
end

-- ---- autoplay ----------------------------------------------------------------------------------

-- The game's AI plays our civ for `turns` turns, then hands it back.
function H.autoplay(turns)
  local me = H.me()
  -- Tutorial advisor popups wait for a click and hold the turn forever (seen live at T17): turn
  -- them off for this session (UserConfiguration only; the saved options are left alone).
  local tutorial = UserConfiguration.GetValue('TutorialLevel')
  if tutorial ~= nil and tutorial ~= -1 then UserConfiguration.SetValue('TutorialLevel', -1) end
  AutoplayManager.SetReturnAsPlayer(me)
  AutoplayManager.SetObserveAsPlayer(me)
  AutoplayManager.SetTurns(turns)
  AutoplayManager.SetActive(true)
  return { active = AutoplayManager.IsActive(), turns = turns, turn = Game.GetCurrentGameTurn() }
end

function H.autoplay_stop()
  AutoplayManager.SetActive(false)
  return { active = AutoplayManager.IsActive(), turn = Game.GetCurrentGameTurn() }
end

function H.autoplay_status()
  return { active = AutoplayManager.IsActive(), turns = AutoplayManager.GetTurns(), turn = Game.GetCurrentGameTurn() }
end
