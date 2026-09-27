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
-- (CityOperationTypes.BUILD with VALUE_EXCLUSIVE), research and civics
-- (UI.RequestPlayerOperation RESEARCH / PROGRESS_CIVIC), policies (UNLOCK_POLICIES, then
-- RequestPolicyChanges; slot types 0 economic, 1 military, 2 diplomatic, 3 wildcard), the build
-- queue's current item (GetCurrentProductionTypeHash), era score (Game.GetEras()) and military
-- strength (GetStats():GetMilitaryStrength()) are ported from civ6-mcp
-- (https://github.com/lmwilki/civ6-mcp), MIT License, Copyright (c) 2026 Liam Wilkinson.
-- Checked live on 1.0.12.68 (games/civ6-kublai/journal.md).

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
  if v == nil then return 'null' end
  if t == 'boolean' then return v and 'true' or 'false' end
  if t == 'number' then
    if v ~= v or v == math.huge or v == -math.huge then return 'null' end
    if v == math.floor(v) and math.abs(v) < 1e15 then return string.format('%d', v) end
    return string.format('%.4g', v)
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

-- Enemy military units (at war with us, or barbarians) within 3 tiles of the city, and whether
-- its City Center is under siege or damaged.
local function threat(me, c)
  local n = 0
  local cx, cy = c:GetX(), c:GetY()
  for dy = -3, 3 do
    for dx = -3, 3 do
      local x, y = cx + dx, cy + dy
      if Map.GetPlotDistance(cx, cy, x, y) <= 3 then
        local units = Map.GetUnitsAt(x, y)
        if units then
          for u in units:Units() do
            local owner = u:GetOwner()
            local row = GameInfo.Units[u:GetType()]
            local military = row and row.FormationClass ~= 'FORMATION_CLASS_CIVILIAN' and row.FormationClass ~= 'FORMATION_CLASS_SUPPORT'
            if owner ~= me and military and (Players[owner]:IsBarbarian() or at_war_with(me, owner)) then
              n = n + 1
            end
          end
        end
      end
    end
  end
  local siege, damaged = false, false
  for _, d in c:GetDistricts():Members() do
    local row = GameInfo.Districts[d:GetType()]
    if row and row.DistrictType == 'DISTRICT_CITY_CENTER' then
      pcall(function() siege = d:IsUnderSiege() end)
      pcall(function() damaged = (d:GetDamage(DefenseTypes.DISTRICT_GARRISON) or 0) > 0 end)
    end
  end
  return n, siege, damaged
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
  local districts, wonders = H.array(), H.array()
  for _, d in c:GetDistricts():Members() do
    local row = GameInfo.Districts[d:GetType()]
    if row and row.DistrictType ~= 'DISTRICT_CITY_CENTER' then
      districts[#districts + 1] = row.DistrictType .. (d:IsComplete() and '' or ' (building)')
    end
  end
  local b = c:GetBuildings()
  for row in GameInfo.Buildings() do
    if row.IsWonder and b:HasBuilding(row.Index) then wonders[#wonders + 1] = row.BuildingType end
  end
  local enemies, siege, damaged = threat(me, c)
  local loyalty = nil
  pcall(function() loyalty = math.floor(c:GetCulturalIdentity():GetLoyalty()) end)
  return {
    id = c:GetID(), name = name_of(c:GetName()), pop = c:GetPopulation(), capital = c:IsCapital(),
    producing = producing, turns_left = turns, districts = districts, wonders = wonders,
    food = c:GetYield(YieldTypes.FOOD), production = c:GetYield(YieldTypes.PRODUCTION),
    enemies_near = enemies, under_siege = siege, damaged = damaged,
    threatened = enemies > 0 or siege or damaged, loyalty = loyalty,
  }
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

local function blocker(me)
  local b = NotificationManager.GetFirstEndTurnBlocking(me)
  if b == nil or b == EndTurnBlockingTypes.NO_ENDTURN_BLOCKING then return nil end
  for k, v in pairs(EndTurnBlockingTypes) do
    if v == b then return k end
  end
  return tostring(b)
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
    options = opt_ok and opt or nil,
    blocker = blocker(me),
    autoplay = { active = AutoplayManager.IsActive(), turns = AutoplayManager.GetTurns() },
  }
end

-- ---- orders ------------------------------------------------------------------------------------

-- Research or civic. In GameCore the setter changes it at once (checked here); in InGame the
-- UI's request is sent instead (seen live: ignored from the tuner, so the controller sends these
-- two orders to GameCore). Every prerequisite must be known: the GameCore setter does not check.
local function progress(kind, key)
  local me = H.me()
  local tbl, getter, op, param, prereqs, col, pcol = 'Technologies', 'GetTechs', 'RESEARCH', 'PARAM_TECH_TYPE',
    'TechnologyPrereqs', 'Technology', 'PrereqTech'
  if kind == 'civic' then
    tbl, getter, op, param, prereqs, col, pcol = 'Civics', 'GetCulture', 'PROGRESS_CIVIC', 'PARAM_CIVIC_TYPE',
      'CivicPrereqs', 'Civic', 'PrereqCivic'
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
  if set then
    set(holder, row.Index)
    local now = kind == 'civic' and holder:GetProgressingCivic() or holder:GetResearchingTech()
    if now ~= row.Index then return fail(key .. ' was not taken by the game') end
    return { set = key }
  end
  local params = {}
  params[PlayerOperations[param]] = row.Index
  UI.RequestPlayerOperation(me, PlayerOperations[op], params)
  return { requested = key }
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

-- The live price of an item in a city, and whether the game allows the purchase now.
function H.get_purchase_cost(city_ref, key, currency)
  local c = H.find_city(city_ref)
  if c == nil then return fail('no city of ours named ' .. tostring(city_ref)) end
  local params, err, cost = purchase_params(c, key, currency)
  if params == nil then return fail(err) end
  local can = CityManager.CanStartCommand(c, CityCommandTypes.PURCHASE, false, params, false)
  local me = H.me()
  local balance = currency == 'faith' and Players[me]:GetReligion():GetFaithBalance() or Players[me]:GetTreasury():GetGoldBalance()
  return { item = key, city = name_of(c:GetName()), currency = currency, cost = cost, balance = balance, allowed = can and true or false }
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
