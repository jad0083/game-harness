-- Harness: the controller's helper library for Civilization VI, run in the game's InGame Lua
-- state through the FireTuner relay (docs/design/2026-09-26-civ6-governor-design.md, ruling 2).
--
-- The controller prepends `local HARNESS_VERSION = "<hash of this file>"` and `local HARNESS_STATE =
-- "<Lua state>"` and sends the whole file; a second install of the same version is a no-op. Every
-- public function prints exactly one JSON line ({"ok": true, ...} or {"ok": false, "error": "..."}),
-- since the tuner returns output only through print(). The controller calls functions with
-- arguments it encodes itself (JSON-style string literals of corpus type keys, numbers); nothing
-- here evaluates text.
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
local OLD = Harness

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

-- One attack of an enemy unit on the City Center's garrison: the game's combat preview (as
-- UnitPanel.lua uses it), else the formula with the unit's strength against the district's defence
-- strength. The preview's DAMAGE_TO is the garrison's share: while walls stand they take the rest
-- (seen live at T134 on Xi'an, walls 100: an Archer and a Warrior previewed 1, a Catapult 0), so a
-- preview of 0 counts only while walls stand; without walls it is no answer.
local function attack_damage(e, kind, d, busy, walls_up)
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
      if type(dmg) == 'number' and (dmg > 0 or walls_up) then return dmg, 'simulated' end
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
  local walls_up = (info.defense or {}).walls_hp ~= nil and info.defense.walls_hp > 0
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
        local dmg, src = attack_damage(e, kind, d, busy, walls_up)
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
  -- the AI's own top 3 for this city (ProductionPanel.lua's call; levers design, ruling 29)
  pcall(function()
    local recs = {}
    for _, r in ipairs(c:GetCityAI():GetBuildRecommendations() or {}) do
      recs[#recs + 1] = { type = type_of_hash(r.BuildItemHash) or tostring(r.BuildItemHash), score = math.floor(r.BuildItemScore + 0.5) }
    end
    table.sort(recs, function(a, b) return a.score > b.score end)
    local top = H.array()
    for i = 1, math.min(3, #recs) do top[i] = recs[i] end
    info.recommend = top
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
    diplomacy = H.diplomacy(),
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

-- ---- last stand (docs/design/2026-09-27-civ6-levers-design.md, rulings 22-27) ------------------
-- A city about to fall gets scripted actions before the AI plays the turn: one action per call, and
-- the governor reads each result back in GameCore (ls_state) before asking for the next. Requests
-- exist only in InGame (checked live at T61); ls_state and finish_moves run in GameCore. The
-- requests themselves are unverified in this build: a request the game ignores shows in the
-- read-back. Cities are named by their numeric ID (GameCore has no Locale for names).

local KILL_MARGIN = 6      -- half of COMBAT_MAX_EXTRA_DAMAGE (12): a planned kill survives bad luck
local LS_RADIUS = 3        -- the stand acts on visible plots within this many tiles of the city
local RETREAT_HP = 40      -- % HP at or below which a unit next to a capturer pulls back

local POPUPS = { 'TechCivicCompletedPopup', 'NaturalWonderPopup', 'NaturalDisasterPopup', 'WonderBuiltPopup',
  'EraCompletePopup', 'HistoricMoments', 'MomentPopup', 'ProjectBuiltPopup', 'RockBandPopup', 'RockBandMoviePopup',
  'InGamePopup', 'GenericPopup', 'PopupDialog', 'BoostUnlockedPopup', 'DiplomacyActionView', 'DiplomacyDealView' }

-- A check that errors counts as failed: the stand acts only when every check answers.
local function check(why, name, fn)
  local ok, bad = pcall(fn)
  if not ok then why[#why + 1] = 'cannot check: ' .. name elseif bad then why[#why + 1] = name end
end

-- Our turn, in our hands, the engine idle and nothing modal on screen. Read-only (InGame).
function H.turn_ready()
  local me = H.me()
  local why = H.array()
  check(why, 'autoplay active', function() return AutoplayManager.IsActive() end)
  check(why, 'not our turn', function() return Game.GetLocalPlayer() ~= me or not Players[me]:IsTurnActive() end)
  check(why, 'turn already sent', function() return UI.HasSentTurnComplete() end)
  check(why, 'engine busy', function() return UI.IsGameCoreBusy() or UI.IsProcessingMessages() end)
  for _, n in ipairs(POPUPS) do
    local ok, ctl = pcall(function() return ContextPtr:LookUpControl('/InGame/' .. n) end)
    if ok and ctl and not ctl:IsHidden() then why[#why + 1] = 'on screen: ' .. n end
  end
  return { ready = #why == 0, why = why, turn = Game.GetCurrentGameTurn() }
end

-- Authoritative damage, moves and attacks of every unit within LS_RADIUS of our city (GameCore;
-- InGame lags after combat). Read-only.
function H.ls_state(city_id)
  local c = H.find_city(city_id)
  if c == nil then return fail('no city of ours with ID ' .. tostring(city_id)) end
  local cx, cy = c:GetX(), c:GetY()
  local units = H.array()
  for i = 0, 63 do
    local p = Players[i]
    if p and p:IsAlive() then
      for _, u in p:GetUnits():Members() do
        local x, y = u:GetX(), u:GetY()
        if x >= 0 and Map.GetPlotDistance(cx, cy, x, y) <= LS_RADIUS then
          units[#units + 1] = { id = u:GetID(), owner = i, x = x, y = y, damage = u:GetDamage(),
                                moves = u:GetMovesRemaining(), attacks = u:GetAttacksRemaining() }
        end
      end
    end
  end
  return { turn = Game.GetCurrentGameTurn(), me = H.me(), units = units }
end

-- Pin a unit the stand used: the hand-back's AI cannot walk it back (GameCore; unverified here).
function H.finish_moves(unit_id)
  local u = Players[H.me()]:GetUnits():FindID(unit_id)
  if u == nil then return fail('no unit of ours with ID ' .. tostring(unit_id)) end
  local before = u:GetMovesRemaining()
  UnitManager.FinishMoves(u)
  return { unit = unit_id, moves_before = before, moves = u:GetMovesRemaining() }
end

-- A target is hostile two ways: its owner is a barbarian or at war with us, and attacking it would
-- not change a war state (IsAttackChangeWarState empty; Civ6Common.lua). Civilians and support
-- units are never targets (the war check alone misses them, E10).
local function hostile_owner(me, owner)
  if owner == me then return false end
  local ok, barb = pcall(function() return Players[owner]:IsBarbarian() end)
  return (ok and barb) or owner == 63 or at_war_with(me, owner)
end

local function war_safe(cid, x, y)
  local ok, res = pcall(CombatManager.IsAttackChangeWarState, cid, x, y)
  return ok and (res == nil or #res == 0)
end

local function marked_plots(res, plots_key, mods_key, is_target)
  local out = {}
  if type(res) ~= 'table' then return out end
  local mods = res[mods_key] or {}
  for i, idx in ipairs(res[plots_key] or {}) do
    if mods[i] == is_target then
      local p = Map.GetPlotByIndex(idx)
      out[p:GetX() .. ',' .. p:GetY()] = true
    end
  end
  return out
end

-- The engine's own combat preview (UnitPanel.lua); it ignores range, so every attack is gated by
-- the game's CanStart check as well.
local function preview(attacker_cid, defender, ctype)
  local ok, r = pcall(CombatManager.SimulateAttackVersus, attacker_cid, defender:GetComponentID(), ctype)
  if not ok or type(r) ~= 'table' then return nil end
  local D = r[CombatResultParameters.DEFENDER]
  if type(D) ~= 'table' then return nil end
  return { dmg = D[CombatResultParameters.DAMAGE_TO] or 0 }
end

-- Target priority (ruling 23), weakest first within a class.
local function priority(e)
  local p = 50
  if e.dist == 1 and (e.kind == 'melee' or e.kind == 'cavalry') then p = 300
  elseif e.kind == 'siege' and e.dist <= 2 then p = 250
  elseif e.dist == 1 then p = 200
  elseif e.dist == 2 then p = 100 end
  return p - e.hp / 10
end

local function hostiles_at(me, x, y)
  local out = {}
  local here = Map.GetUnitsAt(x, y)
  if here then
    for u in here:Units() do
      local row = GameInfo.Units[u:GetType()]
      if is_military(row) and hostile_owner(me, u:GetOwner()) then out[#out + 1] = { u = u, row = row } end
    end
  end
  return out
end

-- Whether a plot holds a district that is not ours. A City Center or an Encampment takes the hit
-- for a unit standing in it, and ruling 23 leaves attacks on cities and districts out, so a unit
-- there is a threat but never a target. Fails closed: a plot that cannot be read counts as one.
local function foreign_district(me, x, y)
  local ok, res = pcall(function()
    local p = Map.GetPlot(x, y)
    return p:GetDistrictType() ~= -1 and p:GetOwner() ~= me
  end)
  return (not ok) or res
end

-- Hostile military units on visible plots within LS_RADIUS (with authoritative HP when the
-- controller passes `damage`, keyed "<owner>:<id>"), and our military units there. `at` holds the
-- targets by plot: not those in another player's district (`foreign_district`).
local function gather(me, c, damage)
  local cx, cy = c:GetX(), c:GetY()
  local enemies, at = {}, {}
  for dy = -LS_RADIUS, LS_RADIUS do
    for dx = -LS_RADIUS, LS_RADIUS do
      local x, y = cx + dx, cy + dy
      local dist = Map.GetPlotDistance(cx, cy, x, y)
      local ok, vis = pcall(function() return PlayersVisibility[me]:IsVisible(x, y) end)
      if dist >= 1 and dist <= LS_RADIUS and ok and vis then
        for _, h in ipairs(hostiles_at(me, x, y)) do
          local u = h.u
          local dmg = damage[u:GetOwner() .. ':' .. u:GetID()] or u:GetDamage()
          local e = { u = u, id = u:GetID(), owner = u:GetOwner(), type = h.row.UnitType, kind = unit_kind(h.row),
                      x = x, y = y, dist = dist, hp = u:GetMaxDamage() - dmg,
                      target = not foreign_district(me, x, y) }
          e.score = priority(e)
          enemies[#enemies + 1] = e
          if e.target then at[x .. ',' .. y] = e end
        end
      end
    end
  end
  table.sort(enemies, function(a, b) return a.score > b.score end)
  local ours = {}
  for _, u in Players[me]:GetUnits():Members() do
    local row = GameInfo.Units[u:GetType()]
    local x, y = u:GetX(), u:GetY()
    if is_military(row) and x >= 0 and Map.GetPlotDistance(cx, cy, x, y) <= LS_RADIUS then
      ours[#ours + 1] = { u = u, id = u:GetID(), type = row.UnitType, kind = unit_kind(row), x = x, y = y,
                          hp = u:GetMaxDamage() - u:GetDamage(), max = u:GetMaxDamage(), moves = u:GetMovesRemaining(),
                          attacks = u:GetAttacksRemaining(), range = u:GetRange(), garrison = (x == cx and y == cy) }
    end
  end
  return enemies, at, ours
end

local function public(e)
  return { id = e.id, owner = e.owner, type = e.type, x = e.x, y = e.y, hp = e.hp }
end

local function at_xy(enum, x, y)
  local t = {}
  t[enum.PARAM_X] = x
  t[enum.PARAM_Y] = y
  return t
end

local function kills(s, e)
  return s ~= nil and s.dmg - KILL_MARGIN >= e.hp
end

-- The best reachable plot for a hurt unit: next to no hostile, empty but for our civilians;
-- +20 an empty city centre, -10 per hostile 2 tiles away, -3 per tile from the city, +5 our
-- territory, +2 hills.
local function best_retreat(me, o, c, enemies)
  local ok, reach = pcall(UnitManager.GetReachableMovement, o.u)
  if not ok or type(reach) ~= 'table' then return nil end
  local best, best_score
  for _, idx in ipairs(reach) do
    local p = Map.GetPlotByIndex(idx)
    local x, y = p:GetX(), p:GetY()
    -- within reach of the stand (and of ls_state's read-back): LS_RADIUS of the city
    local free = not (x == o.x and y == o.y) and Map.GetPlotDistance(x, y, c:GetX(), c:GetY()) <= LS_RADIUS
    for dy = -1, 1 do
      for dx = -1, 1 do
        if free and Map.GetPlotDistance(x, y, x + dx, y + dy) == 1 and #hostiles_at(me, x + dx, y + dy) > 0 then free = false end
      end
    end
    local here = Map.GetUnitsAt(x, y)
    if free and here then
      for other in here:Units() do
        local row = GameInfo.Units[other:GetType()]
        if other:GetOwner() ~= me or (row and row.FormationClass ~= 'FORMATION_CLASS_CIVILIAN') then free = false end
      end
    end
    if free then
      local near2 = 0
      for _, e in ipairs(enemies) do
        if Map.GetPlotDistance(x, y, e.x, e.y) == 2 then near2 = near2 + 1 end
      end
      local hills = false
      pcall(function() hills = p:IsHills() end)
      local score = ((x == c:GetX() and y == c:GetY()) and 20 or 0) - 10 * near2
        - 3 * Map.GetPlotDistance(x, y, c:GetX(), c:GetY()) + (p:GetOwner() == me and 5 or 0) + (hills and 2 or 0)
      if best == nil or score > best_score then best, best_score = { x = x, y = y }, score end
    end
  end
  return best
end

-- One action of a last stand for our city `city_id`, or `done`. `damage` maps "<owner>:<id>" to
-- authoritative damage (from ls_state); `skip` holds "city:<id>" / "unit:<id>" for every actor
-- already used this turn. Priority: city strike (needs walls), ranged and siege attacks (a sure kill
-- first, by the weakest shooter that kills), retreat of a hurt unit (never the garrison).
function H.last_stand_step(city_id, damage, skip)
  local ready = H.turn_ready()
  if not ready.ready then return fail('not ready: ' .. table.concat(ready.why, ', ')) end
  local me = H.me()
  local c = H.find_city(city_id)
  if c == nil then return fail('no city of ours with ID ' .. tostring(city_id)) end
  damage, skip = damage or {}, skip or {}
  local enemies, at, ours = gather(me, c, damage)
  if #enemies == 0 then return { done = true, reason = 'no hostile unit within ' .. LS_RADIUS .. ' tiles' } end

  if not skip['city:' .. c:GetID()] then
    local d = center_of(c)
    local ok, res = pcall(CityManager.GetCommandTargets, c, CityCommandTypes.RANGE_ATTACK)
    local targets = marked_plots(ok and res, CityCommandResults.PLOTS, CityCommandResults.MODIFIERS,
                                 CityCommandResults.MODIFIER_IS_TARGET)
    for _, e in ipairs(enemies) do
      local params = at_xy(CityCommandTypes, e.x, e.y)
      if d and e.target and targets[e.x .. ',' .. e.y] and war_safe(d:GetComponentID(), e.x, e.y)
          and CityManager.CanStartCommand(c, CityCommandTypes.RANGE_ATTACK, params) then
        local s = preview(d:GetComponentID(), e.u, CombatTypes.RANGED)
        CityManager.RequestCommand(c, CityCommandTypes.RANGE_ATTACK, params)
        return { action = 'city_strike', actor = 'city:' .. c:GetID(), target = public(e),
                 predicted_damage = s and s.dmg, predicted_kill = kills(s, e) }
      end
    end
  end

  -- every hostile within the shooter's range, plus the game's target plots (that list can miss valid targets)
  local cands = {}
  for _, o in ipairs(ours) do
    local u = o.u
    if (o.kind == 'ranged' or o.kind == 'siege') and o.moves > 0 and o.attacks > 0 and not skip['unit:' .. o.id] then
      local ctype = (u:GetBombardCombat() > u:GetRangedCombat()) and CombatTypes.BOMBARD or CombatTypes.RANGED
      local seen = {}
      local function consider(e)
        if e == nil or not e.target or seen[e] then return end
        seen[e] = true
        local s = preview(u:GetComponentID(), e.u, ctype)
        local kill = kills(s, e)
        cands[#cands + 1] = { o = o, e = e, s = s, kill = kill,
                              score = e.score + (kill and (1000 - (s.dmg - e.hp)) or (s and s.dmg or 0)) }
      end
      for _, e in ipairs(enemies) do
        if Map.GetPlotDistance(o.x, o.y, e.x, e.y) <= o.range then consider(e) end
      end
      local ok, res = pcall(UnitManager.GetOperationTargets, u, UnitOperationTypes.RANGE_ATTACK)
      for key in pairs(marked_plots(ok and res, UnitOperationResults.PLOTS, UnitOperationResults.MODIFIERS,
                                    UnitOperationResults.MODIFIER_IS_TARGET)) do
        consider(at[key])
      end
    end
  end
  table.sort(cands, function(a, b) return a.score > b.score end)
  for _, cd in ipairs(cands) do
    local params = at_xy(UnitOperationTypes, cd.e.x, cd.e.y)
    if war_safe(cd.o.u:GetComponentID(), cd.e.x, cd.e.y)
        and UnitManager.CanStartOperation(cd.o.u, UnitOperationTypes.RANGE_ATTACK, nil, params) then
      UnitManager.RequestOperation(cd.o.u, UnitOperationTypes.RANGE_ATTACK, params)
      return { action = 'ranged_attack', actor = 'unit:' .. cd.o.id, unit = cd.o.type, target = public(cd.e),
               predicted_damage = cd.s and cd.s.dmg, predicted_kill = cd.kill }
    end
  end

  for _, o in ipairs(ours) do
    if not o.garrison and o.moves > 0 and o.hp * 100 <= RETREAT_HP * o.max and not skip['unit:' .. o.id] then
      local pressed = false
      for _, e in ipairs(enemies) do
        if (e.kind == 'melee' or e.kind == 'cavalry') and Map.GetPlotDistance(o.x, o.y, e.x, e.y) == 1 then pressed = true end
      end
      local dest = pressed and best_retreat(me, o, c, enemies)
      if dest and war_safe(o.u:GetComponentID(), dest.x, dest.y) then
        local params = at_xy(UnitOperationTypes, dest.x, dest.y)
        params[UnitOperationTypes.PARAM_MODIFIERS] = UnitOperationMoveModifiers.NONE
        if UnitManager.CanStartOperation(o.u, UnitOperationTypes.MOVE_TO, nil, params) then
          UnitManager.RequestOperation(o.u, UnitOperationTypes.MOVE_TO, params)
          return { action = 'retreat', actor = 'unit:' .. o.id, unit = o.type, from = { x = o.x, y = o.y }, to = dest,
                   hp = o.hp }
        end
      end
    end
  end
  return { done = true, reason = 'nothing left to do' }
end

-- ---- district placement, read-only (levers design, ruling 30, stage A) ---------------------------
-- Per city: the districts placed, and for each district it could place the plots the game allows
-- (GetOperationTargets with BUILD, as civ6-mcp map.py; unverified here); the plots within 3 tiles
-- (`near`) and the facts of those and their neighbours. A scorer outside the game (src/pilot/
-- civ6_placement.py) rates them; nothing is placed.
-- Keys drop their prefix (TERRAIN_, FEATURE_, RESOURCE_, IMPROVEMENT_, DISTRICT_, BUILDING_).

local function short(tbl, idx, col, prefix)
  if idx == nil or idx < 0 then return nil end
  local row = GameInfo[tbl][idx]
  return row and (row[col]:gsub('^' .. prefix, '')) or nil
end

local function plot_facts(p)
  local f = { x = p:GetX(), y = p:GetY() }
  pcall(function() f.t = short('Terrains', p:GetTerrainType(), 'TerrainType', 'TERRAIN_') end)
  pcall(function() f.f = short('Features', p:GetFeatureType(), 'FeatureType', 'FEATURE_') end)
  pcall(function() f.r = short('Resources', p:GetResourceType(), 'ResourceType', 'RESOURCE_') end)
  pcall(function() f.i = short('Improvements', p:GetImprovementType(), 'ImprovementType', 'IMPROVEMENT_') end)
  pcall(function() f.d = short('Districts', p:GetDistrictType(), 'DistrictType', 'DISTRICT_') end)
  pcall(function() f.w = short('Buildings', p:GetWonderType(), 'BuildingType', 'BUILDING_') end)
  pcall(function() f.o = p:GetOwner() end)
  for k, m in pairs({ river = 'IsRiver', hills = 'IsHills', mountain = 'IsMountain', water = 'IsWater',
                      coast = 'IsCoastalLand', nw = 'IsNaturalWonder' }) do
    pcall(function() if p[m](p) then f[k] = true end end)
  end
  return f
end

function H.district_plots(city_id)
  local me = H.me()
  local cities, plots = H.array(), {}
  local function add(p, with_adj)
    local key = tostring(p:GetIndex())
    plots[key] = plots[key] or plot_facts(p)
    if with_adj and plots[key].adj == nil then
      local adj = H.array()
      for dy = -1, 1 do
        for dx = -1, 1 do
          local q = Map.GetPlot(p:GetX() + dx, p:GetY() + dy)
          if q and Map.GetPlotDistance(p:GetX(), p:GetY(), q:GetX(), q:GetY()) == 1 then
            adj[#adj + 1] = q:GetIndex()
            add(q, false)
          end
        end
      end
      plots[key].adj = adj
    end
  end
  for _, c in Players[me]:GetCities():Members() do
    if city_id == nil or c:GetID() == city_id then
      local cx, cy, near = c:GetX(), c:GetY(), H.array()
      for dy = -3, 3 do
        for dx = -3, 3 do
          local p = Map.GetPlot(cx + dx, cy + dy)
          if p and Map.GetPlotDistance(cx, cy, p:GetX(), p:GetY()) <= 3 then
            add(p, true)
            near[#near + 1] = p:GetIndex()
          end
        end
      end
      local placed = H.array()
      for _, d in c:GetDistricts():Members() do
        local row = GameInfo.Districts[d:GetType()]
        if row then
          placed[#placed + 1] = { type = row.DistrictType, x = d:GetX(), y = d:GetY(), complete = d:IsComplete() }
        end
      end
      local bq, cands = c:GetBuildQueue(), H.array()
      for row in GameInfo.Districts() do
        if row.DistrictType ~= 'DISTRICT_CITY_CENTER' and not bq:HasBeenPlaced(row.Hash) and bq:CanProduce(row.Hash, true) then
          local e = { type = row.DistrictType, plots = H.array() }
          local ok, err = pcall(function()
            local params = {}
            params[CityOperationTypes.PARAM_DISTRICT_TYPE] = row.Hash
            local res = CityManager.GetOperationTargets(c, CityOperationTypes.BUILD, params)
            for _, idx in ipairs((res or {})[CityOperationResults.PLOTS] or {}) do
              e.plots[#e.plots + 1] = idx
              add(Map.GetPlotByIndex(idx), true)
            end
          end)
          if not ok then e.error = tostring(err) end
          cands[#cands + 1] = e
        end
      end
      cities[#cities + 1] = { id = c:GetID(), name = name_of(c:GetName()), x = cx, y = cy, near = near,
                              placed = placed, candidates = cands }
    end
  end
  -- a plot shows a wonder while it is still being built: only these count as built
  local built = H.array()
  pcall(function()
    for _, c in Players[me]:GetCities():Members() do
      local b = c:GetBuildings()
      for row in GameInfo.Buildings() do
        if row.IsWonder and b:HasBuilding(row.Index) then built[#built + 1] = (row.BuildingType:gsub('^BUILDING_', '')) end
      end
    end
  end)
  return { turn = Game.GetCurrentGameTurn(), player = me, cities = cities, plots = plots, built = built }
end

-- ---- diplomacy auto-reply (issues.md T240, T342) ----------------------------------------------
-- An AI leader's statement to us opens DiplomacyActionView, which locks the engine
-- (UI.ReferenceCurrentEvent) until a human answers, so an autoplay turn never ends. popups.toml
-- removes the view's handler; this one, in InGame only, answers while autoplay runs. The first
-- statement of a session gets its reply below; every later one (the AI's "Thank you.") gets Goodbye,
-- the only choice a follow-up offers. POSITIVE is the view's AddResponse key; EXIT is Goodbye
-- (CloseSession); REFUSE is the deal view's refusal (AddResponse NEGATIVE). A POSITIVE is sent only
-- when the game's data offers it for that statement without a DiplomaticActionType (the troop
-- warning's other choice declares war); else Goodbye. An unknown kind gets Goodbye. Outside
-- autoplay a statement waits until autoplay next starts. The last 20 are logged for the snapshot.
local DIPLOMACY = {}
H.DIPLOMACY = DIPLOMACY
for reply, kinds in pairs({
  -- promises: the conciliatory choice (the other costs grievances or, for troops, is a surprise war)
  POSITIVE = 'WARNING_TOO_MANY_TROOPS_NEAR_ME WARNING_DONT_SETTLE_NEAR_ME WARNING_STOP_SPYING_ON_ME '
    .. 'WARNING_STOP_DIGGING_UP_ARTIFACTS WARNING_STOP_CONVERTING_MY_CITIES',
  REFUSE = 'MAKE_DEAL MAKE_DEMAND',              -- nothing is given away
  -- proposals (no safe accept rule is proven) and first meetings: Goodbye, neither yes nor no;
  -- kudos, warnings, denouncements, war declarations and defeats offer only Goodbye
  EXIT = 'DECLARE_FRIEND DIPLOMATIC_DELEGATION RESIDENT_EMBASSY OPEN_BORDERS MAKE_ALLIANCE RENEW_ALLIANCE '
    .. 'MAKE_PEACE FIRST_MEET_NEAR_RECIPIENT FIRST_MEET_VISIT_RECIPIENT FIRST_MEET_NEAR_INITIATOR FIRST_MEET_NO_MANS '
    .. 'FIRST_MEET_NO_MANS_INFO_EXCHANGE DIPLOMATIC_KUDO DIPLOMATIC_WARNING DIPLOMATIC_HIDDEN_AGENDA_KUDO '
    .. 'DIPLOMATIC_HIDDEN_AGENDA_WARNING DENOUNCE DEFEAT DECLARE_WAR_OF_RETRIBUTION DECLARE_JOINT_WAR_OF_RETRIBUTION',
}) do
  for k in kinds:gmatch('%S+') do DIPLOMACY[k] = reply end
end
for w in ('SURPRISE FORMAL HOLY RECONQUEST LIBERATION PROTECTORATE COLONIAL TERRITORIAL GOLDEN_AGE EMERGENCY IDEOLOGICAL '
    .. 'JOINT_FORMAL JOINT_HOLY JOINT_RECONQUEST JOINT_LIBERATION JOINT_PROTECTORATE JOINT_COLONIAL JOINT_TERRITORIAL '
    .. 'JOINT_GOLDEN_AGE JOINT_IDEOLOGICAL'):gmatch('%S+') do
  DIPLOMACY['DECLARE_' .. w .. '_WAR'] = 'EXIT'
end

-- log, sessions waiting for autoplay, sessions answered and not closed (kept across reinstalls)
local D = OLD and OLD.dipl or { n = 0, log = {}, wait = {}, open = {} }
H.dipl = D

-- Numbers an entry and logs it (the last 20 stay).
local function add_log(e)
  D.n = D.n + 1
  e.n = D.n
  table.insert(D.log, e)
  if #D.log > 20 then table.remove(D.log, 1) end
  return e
end

local function offered(kind, reply)
  local set
  for r in GameInfo.DiplomacyStatements() do
    if r.Type == kind and r.Initiator == 'AI' and r.SubType == 'NONE' then set = r.Selections end
  end
  for r in GameInfo.DiplomacySelections() do
    if set and r.Type == set and r.Key == 'CHOICE_' .. reply then return r.DiplomaticActionType == nil end
  end
  return false
end

local function reply_for(e)
  if (e.sub or 'NONE') ~= 'NONE' or D.open[e.session] then return 'EXIT', 'follow-up' end
  local r = DIPLOMACY[e.kind]
  if r == nil then return 'EXIT', 'unknown' end
  if r == 'POSITIVE' then
    local ok, yes = pcall(offered, e.kind, r)
    if not (ok and yes) then return 'EXIT', 'guard' end
  end
  return r, 'table'
end

-- The session is listed as open before any call and leaves the list only once Goodbye went through,
-- so whatever fails here, the next autoplay start closes it. A failed answer gets Goodbye at once
-- (`closed` when that worked).
local function respond(e)
  e.reply, e.why = reply_for(e)
  e.at = Game.GetCurrentGameTurn()
  if e.session ~= nil then D.open[e.session] = e end
  local function goodbye()
    DiplomacyManager.CloseSession(e.session)
    D.open[e.session] = nil
  end
  local ok, err
  if e.reply == 'EXIT' then
    ok, err = pcall(goodbye)
  else
    ok, err = pcall(function()
      DiplomacyManager.AddResponse(e.session, H.me(), e.reply == 'REFUSE' and 'NEGATIVE' or e.reply)
    end)
    if not ok and pcall(goodbye) then e.closed = true end
  end
  if not ok then e.err = tostring(err) end
end

local function on_statement(from, to, kv)
  if Harness ~= H then return end                 -- a replaced library's handler left behind
  pcall(function()
    local me = H.me()
    if to ~= me or from == me then return end
    -- logged before it is read, so a failed read still shows (with `err`) and gets Goodbye (unknown kind)
    local e = add_log({ turn = Game.GetCurrentGameTurn(), from = from, session = kv.SessionID })
    local ok, err = pcall(function()
      e.session = e.session or DiplomacyManager.FindOpenSessionID(me, from)
      e.kind = DiplomacyManager.GetKeyName(kv.StatementType)
      e.sub = DiplomacyManager.GetKeyName(kv.StatementSubType)
    end)
    if not ok then e.err = tostring(err) end
    pcall(function() e.civ = PlayerConfigurations[from]:GetCivilizationTypeName() end)
    if AutoplayManager.IsActive() then
      respond(e)
    else
      e.why = 'waiting'
      D.wait[e.session] = e
    end
  end)
end

-- The sweep's log entry for each answered session it closes: one per session, even when retried.
local swept = setmetatable({}, { __mode = 'k' })

-- When autoplay starts: answer the statements that waited (a follow-up of an answered session, such
-- as a "Thank you." that came after the hand-back, gets Goodbye as one), then close the sessions
-- answered before this start that no follow-up closed. That Goodbye is logged too (why 'sweep'); a
-- failed one keeps its session listed and is tried again at the next start.
local function dipl_sweep()
  local before = {}
  for sid, e in pairs(D.open) do before[sid] = e end
  for sid, e in pairs(D.wait) do
    D.wait[sid] = nil
    if DiplomacyManager.IsSessionIDOpen(sid) then
      e.late = true
      respond(e)
    else
      e.why = 'gone'
    end
  end
  for sid, e in pairs(before) do
    if D.open[sid] == e then
      if DiplomacyManager.IsSessionIDOpen(sid) then
        local s = swept[e] or add_log({ turn = e.turn, from = e.from, civ = e.civ, session = sid, kind = e.kind,
                                        sub = e.sub, reply = 'EXIT', why = 'sweep' })
        swept[e] = s
        s.at = Game.GetCurrentGameTurn()
        local ok, err = pcall(DiplomacyManager.CloseSession, sid)
        s.err = (not ok) and tostring(err) or nil
        if ok then D.open[sid] = nil end
      else
        D.open[sid] = nil
      end
    end
  end
end

if HARNESS_STATE == 'InGame' then
  if OLD and OLD.dipl_handler then pcall(function() Events.DiplomacyStatement.Remove(OLD.dipl_handler) end) end
  if pcall(function() Events.DiplomacyStatement.Add(on_statement) end) then H.dipl_handler = on_statement end
end

function H.diplomacy()
  local log = H.array()
  for i, e in ipairs(D.log) do log[i] = e end
  return { handler = H.dipl_handler ~= nil, log = log }
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
  pcall(dipl_sweep)                 -- after SetActive: an answer's follow-up is then answered at once
  return { active = AutoplayManager.IsActive(), turns = turns, turn = Game.GetCurrentGameTurn() }
end

function H.autoplay_stop()
  AutoplayManager.SetActive(false)
  return { active = AutoplayManager.IsActive(), turn = Game.GetCurrentGameTurn() }
end

function H.autoplay_status()
  return { active = AutoplayManager.IsActive(), turns = AutoplayManager.GetTurns(), turn = Game.GetCurrentGameTurn() }
end
