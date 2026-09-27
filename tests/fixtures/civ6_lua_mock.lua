-- Stand-ins for the parts of Civilization VI's InGame Lua API that corpora/civ6/lua/harness.lua
-- reads, enough to run Harness.snapshot outside the game (tests/test_harness_lua.py, LuaJIT via
-- lupa). It proves syntax and control flow only: API names and results are checked live.
--
-- The world: player 0 (China) with Beijing at 22,21 (no garrison, no walls, a barbarian Spearman
-- and Warrior adjacent, a peaceful Scout 3 tiles away) and Xi'an at 26,13 (an Archer on its tile,
-- the City Center damaged). Tests change MOCK before calling the snapshot.

local function hash(s)
  local h = 0
  for i = 1, #s do h = (h * 31 + s:byte(i)) % 2147483647 end
  return h
end

-- A GameInfo table: rows by type key and by index, and `for row in T() do`.
local function tbl(rows, keycol)
  local by = {}
  for i, r in ipairs(rows) do
    r.Index = i - 1
    r.Hash = r.Hash or hash(r[keycol])
    by[r[keycol]] = r
    by[i - 1] = r
  end
  return setmetatable({}, {
    __index = function(_, k) return by[k] end,
    __call = function() local i = 0 return function() i = i + 1 return rows[i] end end,
  })
end

local function members(list)
  return { Members = function() local i = 0 return function() i = i + 1 if list[i] then return i, list[i] end end end }
end

MOCK = { busy = false, simulate_fails = false, simulate_zero = false, religion_fails = false, turn = 61, walls = 0 }

GameInfo = {
  Units = tbl({
    { UnitType = 'UNIT_WARRIOR', FormationClass = 'FORMATION_CLASS_LAND_COMBAT', PromotionClass = 'PROMOTION_CLASS_MELEE', Domain = 'DOMAIN_LAND', Combat = 20, RangedCombat = 0, Bombard = 0 },
    { UnitType = 'UNIT_ARCHER', FormationClass = 'FORMATION_CLASS_LAND_COMBAT', PromotionClass = 'PROMOTION_CLASS_RANGED', Domain = 'DOMAIN_LAND', Combat = 15, RangedCombat = 25, Bombard = 0 },
    { UnitType = 'UNIT_SPEARMAN', FormationClass = 'FORMATION_CLASS_LAND_COMBAT', PromotionClass = 'PROMOTION_CLASS_ANTI_CAVALRY', Domain = 'DOMAIN_LAND', Combat = 25, RangedCombat = 0, Bombard = 0 },
    { UnitType = 'UNIT_SCOUT', FormationClass = 'FORMATION_CLASS_LAND_COMBAT', PromotionClass = 'PROMOTION_CLASS_RECON', Domain = 'DOMAIN_LAND', Combat = 10, RangedCombat = 0, Bombard = 0 },
    { UnitType = 'UNIT_HORSEMAN', FormationClass = 'FORMATION_CLASS_LAND_COMBAT', PromotionClass = 'PROMOTION_CLASS_LIGHT_CAVALRY', Domain = 'DOMAIN_LAND', Combat = 36, RangedCombat = 0, Bombard = 0 },
    { UnitType = 'UNIT_CATAPULT', FormationClass = 'FORMATION_CLASS_LAND_COMBAT', PromotionClass = 'PROMOTION_CLASS_SIEGE', Domain = 'DOMAIN_LAND', Combat = 25, RangedCombat = 0, Bombard = 35 },
    { UnitType = 'UNIT_SETTLER', FormationClass = 'FORMATION_CLASS_CIVILIAN', Domain = 'DOMAIN_LAND', Combat = 0, RangedCombat = 0, Bombard = 0 },
    { UnitType = 'UNIT_GALLEY', FormationClass = 'FORMATION_CLASS_NAVAL', PromotionClass = 'PROMOTION_CLASS_NAVAL_MELEE', Domain = 'DOMAIN_SEA', Combat = 30, RangedCombat = 0, Bombard = 0 },
  }, 'UnitType'),
  Buildings = tbl({
    { BuildingType = 'BUILDING_MONUMENT', IsWonder = false },
    { BuildingType = 'BUILDING_GRANARY', IsWonder = false },
    { BuildingType = 'BUILDING_WALLS', IsWonder = false },
    { BuildingType = 'BUILDING_PYRAMIDS', IsWonder = true },
  }, 'BuildingType'),
  Districts = tbl({ { DistrictType = 'DISTRICT_CITY_CENTER' }, { DistrictType = 'DISTRICT_HOLY_SITE' } }, 'DistrictType'),
  Projects = tbl({ { ProjectType = 'PROJECT_ENHANCE_DISTRICT_HOLY_SITE' } }, 'ProjectType'),
  Technologies = tbl({ { TechnologyType = 'TECH_POTTERY' }, { TechnologyType = 'TECH_WRITING' } }, 'TechnologyType'),
  Civics = tbl({ { CivicType = 'CIVIC_CODE_OF_LAWS' }, { CivicType = 'CIVIC_STATE_WORKFORCE' } }, 'CivicType'),
  Policies = tbl({ { PolicyType = 'POLICY_SURVEY' }, { PolicyType = 'POLICY_GOD_KING' } }, 'PolicyType'),
  Governments = tbl({ { GovernmentType = 'GOVERNMENT_CHIEFDOM' } }, 'GovernmentType'),
  Eras = tbl({ { EraType = 'ERA_ANCIENT' }, { EraType = 'ERA_CLASSICAL' } }, 'EraType'),
  Beliefs = tbl({ { BeliefType = 'BELIEF_INITIATION_RITES' } }, 'BeliefType'),
  Religions = tbl({ { ReligionType = 'RELIGION_PANTHEON', Pantheon = true }, { ReligionType = 'RELIGION_BUDDHISM', Pantheon = false } }, 'ReligionType'),
  Maps = tbl({ { MapSizeType = 'MAPSIZE_SMALL' } }, 'MapSizeType'),
  Map_GreatPersonClasses = tbl({ { MapSizeType = 'MAPSIZE_SMALL', GreatPersonClassType = 'GREAT_PERSON_CLASS_PROPHET', MaxWorldInstances = 4, Key = 'a' } }, 'Key'),
  GreatPersonClasses = tbl({ { GreatPersonClassType = 'GREAT_PERSON_CLASS_GENERAL' }, { GreatPersonClassType = 'GREAT_PERSON_CLASS_PROPHET' } }, 'GreatPersonClassType'),
  Yields = tbl({ { YieldType = 'YIELD_GOLD' }, { YieldType = 'YIELD_FAITH' } }, 'YieldType'),
}

YieldTypes = { FOOD = 0, PRODUCTION = 1 }
DefenseTypes = { DISTRICT_GARRISON = 11, DISTRICT_OUTER = 12 }
CityCommandTypes = { PURCHASE = 21, RANGE_ATTACK = 22, PARAM_UNIT_TYPE = 23, PARAM_BUILDING_TYPE = 24, PARAM_YIELD_TYPE = 25,
                     PARAM_MILITARY_FORMATION_TYPE = 26, PARAM_X = 27, PARAM_Y = 28 }
CityCommandResults = { PLOTS = 31, MODIFIERS = 32, MODIFIER_IS_TARGET = 33 }
MilitaryFormationTypes = { STANDARD_MILITARY_FORMATION = 0 }
CombatTypes = { MELEE = 41, RANGED = 42, BOMBARD = 43 }
CombatResultParameters = { ATTACKER = 51, DEFENDER = 52, DAMAGE_TO = 53 }
EndTurnBlockingTypes = { NO_ENDTURN_BLOCKING = 0, ENDTURN_BLOCKING_UNITS = 61, ENDTURN_BLOCKING_COMMEMORATION_AVAILABLE = 62 }

-- ---- units ---------------------------------------------------------------------------------------

UNITS = {}
local U = {}
U.__index = U
function U:GetX() return self.x end
function U:GetY() return self.y end
function U:GetID() return self.id end
function U:GetOwner() return self.owner end
function U:GetType() return self.utype end
function U:GetDamage() return self.dmg or 0 end
function U:GetMaxDamage() return 100 end
function U:GetMovesRemaining() return self.moves or 2 end
function U:GetAttacksRemaining() return self.attacks or 1 end
function U:GetRange() return self.range or 0 end
function U:GetCombat() return GameInfo.Units[self.utype].Combat end
function U:GetRangedCombat() return GameInfo.Units[self.utype].RangedCombat end
function U:GetBombardCombat() return GameInfo.Units[self.utype].Bombard end
function U:GetComponentID() return { player = self.owner, id = self.id } end
function unit(t) setmetatable(t, U) UNITS[#UNITS + 1] = t return t end

BARB = 63
unit { id = 1, owner = BARB, utype = 'UNIT_SPEARMAN', x = 23, y = 21, dmg = 69 }
unit { id = 2, owner = BARB, utype = 'UNIT_WARRIOR', x = 23, y = 22 }
unit { id = 3, owner = 4, utype = 'UNIT_SCOUT', x = 25, y = 21, dmg = 30 }        -- peaceful major: not an enemy
unit { id = 4, owner = BARB, utype = 'UNIT_CATAPULT', x = 24, y = 21, range = 2 } -- siege, 2 tiles from Beijing
unit { id = 10, owner = 0, utype = 'UNIT_ARCHER', x = 26, y = 13, range = 2 }     -- Xi'an's garrison
unit { id = 11, owner = 0, utype = 'UNIT_WARRIOR', x = 21, y = 22, dmg = 50, moves = 1 }
unit { id = 12, owner = 0, utype = 'UNIT_SETTLER', x = 22, y = 21 }               -- a civilian is no garrison

Map = {}
function Map.GetPlotDistance(x1, y1, x2, y2)     -- odd-r offset hex distance
  local function cube(x, y) local q = x - (y - (y % 2)) / 2 return q, y, -q - y end
  local a, b, c = cube(x1, y1)
  local d, e, f = cube(x2, y2)
  return math.max(math.abs(a - d), math.abs(b - e), math.abs(c - f))
end
function Map.GetUnitsAt(x, y)
  local list = {}
  for _, u in ipairs(UNITS) do if u.x == x and u.y == y then list[#list + 1] = u end end
  if #list == 0 then return nil end
  return { Units = function() local i = 0 return function() i = i + 1 return list[i] end end }
end
function Map.GetMapSize() return 0 end

-- ---- cities --------------------------------------------------------------------------------------

local function district(dtype, x, y, garrison_damage, walls)
  return {
    GetType = function() return GameInfo.Districts[dtype].Index end,
    IsComplete = function() return true end,
    IsUnderSiege = function() return false end,
    GetX = function() return x end, GetY = function() return y end,
    GetDamage = function(_, dt) return dt == DefenseTypes.DISTRICT_GARRISON and garrison_damage or 0 end,
    GetMaxDamage = function(_, dt) return dt == DefenseTypes.DISTRICT_GARRISON and 200 or (walls or MOCK.walls) end,
    GetComponentID = function() return { district = dtype } end,
    GetDefenseStrength = function() return 28 end,
  }
end

local function city(t)
  local d = district('DISTRICT_CITY_CENTER', t.x, t.y, t.garrison_damage or 0, t.walls)
  local producing = GameInfo.Units[t.producing] or GameInfo.Buildings[t.producing]
  return {
    GetID = function() return t.id end, GetName = function() return t.name end,
    GetX = function() return t.x end, GetY = function() return t.y end,
    GetPopulation = function() return 3 end, IsCapital = function() return t.capital or false end,
    GetYield = function() return 4 end,
    GetCulturalIdentity = function() return { GetLoyalty = function() return 100 end } end,
    GetDistricts = function() return members({ d }) end,
    GetBuildings = function() return { HasBuilding = function(_, i) return t.buildings[i] or false end } end,
    GetGold = function()
      return { GetPurchaseCost = function(_, y, h)
        for row in GameInfo.Units() do
          if row.Hash == h then
            local gold = ({ UNIT_WARRIOR = 160, UNIT_ARCHER = 240, UNIT_SPEARMAN = 260, UNIT_HORSEMAN = 320 })[row.UnitType] or 999
            return y == GameInfo.Yields.YIELD_FAITH.Index and gold / 2 or gold
          end
        end
        return 500
      end }
    end,
    GetBuildQueue = function()
      return {
        GetSize = function() return producing and 1 or 0 end,
        GetCurrentProductionTypeHash = function() return producing.Hash end,
        GetTurnsLeft = function() return 3 end,
        HasBeenPlaced = function() return false end,
        CanProduce = function(_, h)
          for _, k in ipairs(t.can_build) do
            local row = GameInfo.Units[k] or GameInfo.Buildings[k]
            if row.Hash == h then return true end
          end
          return false
        end,
      }
    end,
  }
end

CITIES = {
  city { id = 65536, name = 'LOC_CITY_BEIJING', x = 22, y = 21, capital = true, producing = 'UNIT_WARRIOR',
         can_build = { 'UNIT_WARRIOR', 'UNIT_ARCHER', 'UNIT_SPEARMAN', 'UNIT_SETTLER', 'BUILDING_GRANARY' },
         buildings = { [GameInfo.Buildings.BUILDING_MONUMENT.Index] = true, [GameInfo.Buildings.BUILDING_PYRAMIDS.Index] = true } },
  city { id = 262147, name = 'LOC_CITY_XIAN', x = 26, y = 13, producing = 'BUILDING_GRANARY', garrison_damage = 40,
         can_build = { 'UNIT_WARRIOR', 'UNIT_ARCHER', 'BUILDING_GRANARY' }, buildings = {} },
}

-- ---- players -------------------------------------------------------------------------------------

Players = {}
local function player(id, major)
  local p = {}
  function p:IsBarbarian() return id == BARB end
  function p:IsAlive() return true end
  function p:IsMajor() return major end
  function p:IsFreeCities() return false end
  function p:GetDiplomacy()
    return { IsAtWarWith = function() return false end, HasMet = function() return true end }
  end
  function p:GetUnits()
    local l = {}
    for _, u in ipairs(UNITS) do if u.owner == id then l[#l + 1] = u end end
    return members(l)
  end
  function p:GetCities() return members(id == 0 and CITIES or {}) end
  function p:GetTechs()
    return { HasTech = function() return false end, CanResearch = function() return true end,
             GetResearchingTech = function() return 0 end, GetTurnsLeft = function() return 4 end,
             GetScienceYield = function() return 9.5 end }
  end
  function p:GetCulture()
    return { HasCivic = function() return false end, CanProgress = function() return true end,
             IsPolicyUnlocked = function() return true end, IsPolicyObsolete = function() return false end,
             IsPolicyActive = function(_, i) return i == 1 end, GetProgressingCivic = function() return -1 end,
             GetCurrentGovernment = function() return 0 end, GetNumPolicySlots = function() return 1 end,
             GetSlotPolicy = function() return 1 end, GetSlotType = function() return 0 end,
             GetCostToUnlockPolicies = function() return 0 end, GetTurnsLeft = function() return 0 end,
             GetCultureYield = function() return 5 end }
  end
  function p:GetTreasury()
    return { GetGoldBalance = function() return 280 end, GetGoldYield = function() return 8 end,
             GetTotalMaintenance = function() return 9.6 end }
  end
  function p:GetReligion()
    if MOCK.religion_fails then
      return { GetFaithYield = function() return 4 end, GetFaithBalance = function() return 388 end }
    end
    return { GetFaithYield = function() return 4 end, GetFaithBalance = function() return 388 end,
             GetPantheon = function() return -1 end, CanCreatePantheon = function() return true end,
             GetReligionTypeCreated = function() return -1 end }
  end
  function p:GetScore() return 120 end
  function p:GetStats()
    return { GetMilitaryStrength = function() return 240 end, GetNumTechsResearched = function() return 14 end,
             GetNumCivicsCompleted = function() return 8 end }
  end
  function p:GetGreatPeoplePoints() return { GetPointsTotal = function(_, i) return i == 1 and 31.6 or 0 end } end
  Players[id] = p
  return p
end
for i = 0, 62 do player(i, i < 8) end
player(BARB, false)

PlayerConfigurations = setmetatable({}, { __index = function()
  return { GetCivilizationTypeName = function() return 'CIVILIZATION_CHINA' end,
           GetLeaderTypeName = function() return 'LEADER_KUBLAI_KHAN_CHINA' end,
           GetCivilizationShortDescription = function() return 'LOC_CIV_CHINA' end,
           GetLeaderName = function() return 'LOC_LEADER_KUBLAI' end }
end })
MapConfiguration = { GetValue = function() return 702403662 end }
local NAMES = { LOC_CITY_BEIJING = 'Beijing', LOC_CITY_XIAN = "Xi'an", LOC_CIV_CHINA = 'China',
                LOC_LEADER_KUBLAI = 'Kublai Khan (China)' }
Locale = { Lookup = function(s) return NAMES[s] or s end }

Game = {
  GetLocalPlayer = function() return 0 end,
  GetCurrentGameTurn = function() return MOCK.turn end,
  GetEras = function()
    return { GetCurrentEra = function() return 0 end, GetPlayerCurrentScore = function() return 20 end,
             GetPlayerDarkAgeThreshold = function() return 24 end, GetPlayerGoldenAgeThreshold = function() return 36 end }
  end,
  GetGreatPeople = function()
    return { GetTimeline = function() return { { Class = 1, Cost = 60 } } end, GetPastTimeline = function() return {} end }
  end,
  GetReligion = function()
    return { GetReligions = function() return { { Religion = 1 } } end, HasBeenFounded = function() return true end,
             GetMinimumFaithNextPantheon = function() return 25 end }
  end,
}

AutoplayManager = { IsActive = function() return false end, GetTurns = function() return 0 end,
                    GetReturnAsPlayer = function() return 0 end }
NotificationManager = {
  GetFirstEndTurnBlocking = function() return EndTurnBlockingTypes.ENDTURN_BLOCKING_COMMEMORATION_AVAILABLE end,
  GetAllEndTurnBlocking = function()
    return { EndTurnBlockingTypes.ENDTURN_BLOCKING_COMMEMORATION_AVAILABLE, EndTurnBlockingTypes.ENDTURN_BLOCKING_UNITS }
  end,
}
UI = { IsGameCoreBusy = function() return MOCK.busy end }

-- a land unit on the city tile: the game refuses a land-unit purchase there (stacking)
CityManager = {
  CanStartCommand = function(c, cmd, _, params)
    if cmd ~= CityCommandTypes.PURCHASE then return false end
    local units = Map.GetUnitsAt(c:GetX(), c:GetY())
    if units then
      for u in units:Units() do
        if u:GetOwner() == 0 and GameInfo.Units[u:GetType()].FormationClass == 'FORMATION_CLASS_LAND_COMBAT' then return false end
      end
    end
    return params[CityCommandTypes.PARAM_YIELD_TYPE] ~= nil
  end,
  GetCommandTargets = function() return { [CityCommandResults.PLOTS] = {}, [CityCommandResults.MODIFIERS] = {} } end,
}
CombatManager = {
  SimulateAttackVersus = function(attacker)
    if MOCK.simulate_fails then error('no combat preview here') end
    local u
    for _, x in ipairs(UNITS) do if x.id == attacker.id then u = x end end
    local r = {}
    local dmg = MOCK.simulate_zero and 0 or ({ [1] = 18, [2] = 15, [4] = 40 })[u.id] or 0
    r[CombatResultParameters.DEFENDER] = { [CombatResultParameters.DAMAGE_TO] = dmg }
    return r
  end,
}
