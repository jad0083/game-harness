-- Hand-written miniature of the game's gameplay schema (only the columns the extractor reads).
CREATE TABLE "Types" ("Type" TEXT NOT NULL, "Kind" TEXT NOT NULL, PRIMARY KEY("Type"));
CREATE TABLE "Eras" ("EraType" TEXT NOT NULL, "Name" TEXT, "Description" TEXT, "ChronologyIndex" INTEGER,
  "GreatPersonBaseCost" INTEGER, "WarmongerPoints" INTEGER, PRIMARY KEY("EraType"));
CREATE TABLE "Yields" ("YieldType" TEXT NOT NULL, "Name" TEXT, PRIMARY KEY("YieldType"));
CREATE TABLE "Terrains" ("TerrainType" TEXT NOT NULL, "Name" TEXT, "MovementCost" INTEGER DEFAULT 1,
  "DefenseModifier" INTEGER DEFAULT 0, "Appeal" INTEGER DEFAULT 0, "Hills" BOOLEAN DEFAULT 0,
  "Mountain" BOOLEAN DEFAULT 0, "Water" BOOLEAN DEFAULT 0, "Impassable" BOOLEAN DEFAULT 0, PRIMARY KEY("TerrainType"));
CREATE TABLE "Technologies" ("TechnologyType" TEXT NOT NULL, "Name" TEXT, "Cost" INTEGER, "Repeatable" BOOLEAN DEFAULT 0,
  "Description" TEXT, "EraType" TEXT, PRIMARY KEY("TechnologyType"),
  FOREIGN KEY ("TechnologyType") REFERENCES "Types"("Type") ON DELETE CASCADE ON UPDATE CASCADE);
CREATE TABLE "TechnologyPrereqs" ("Technology" TEXT NOT NULL, "PrereqTech" TEXT NOT NULL,
  PRIMARY KEY("Technology", "PrereqTech"),
  FOREIGN KEY ("Technology") REFERENCES "Technologies"("TechnologyType") ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY ("PrereqTech") REFERENCES "Technologies"("TechnologyType") ON DELETE CASCADE ON UPDATE CASCADE);
CREATE TABLE "TechnologyModifiers" ("TechnologyType" TEXT NOT NULL, "ModifierId" TEXT NOT NULL);
CREATE TABLE "Boosts" ("BoostID" INTEGER NOT NULL, "TechnologyType" TEXT, "CivicType" TEXT, "Boost" INTEGER,
  "TriggerDescription" TEXT, PRIMARY KEY("BoostID"));
CREATE TABLE "Traits" ("TraitType" TEXT NOT NULL, "Name" TEXT, "Description" TEXT, PRIMARY KEY("TraitType"));
CREATE TABLE "Civilizations" ("CivilizationType" TEXT NOT NULL, "Name" TEXT, "StartingCivilizationLevelType" TEXT,
  PRIMARY KEY("CivilizationType"));
CREATE TABLE "Leaders" ("LeaderType" TEXT NOT NULL, "Name" TEXT, "InheritFrom" TEXT, PRIMARY KEY("LeaderType"));
CREATE TABLE "CivilizationLeaders" ("LeaderType" TEXT NOT NULL, "CivilizationType" TEXT NOT NULL, "CapitalName" TEXT,
  PRIMARY KEY("LeaderType", "CivilizationType"));
CREATE TABLE "CivilizationTraits" ("CivilizationType" TEXT NOT NULL, "TraitType" TEXT NOT NULL,
  PRIMARY KEY("CivilizationType", "TraitType"));
CREATE TABLE "LeaderTraits" ("LeaderType" TEXT NOT NULL, "TraitType" TEXT NOT NULL, PRIMARY KEY("LeaderType", "TraitType"));
CREATE TABLE "Units" ("UnitType" TEXT NOT NULL, "Name" TEXT, "BaseSightRange" INTEGER DEFAULT 2, "BaseMoves" INTEGER,
  "Combat" INTEGER DEFAULT 0, "RangedCombat" INTEGER DEFAULT 0, "Range" INTEGER DEFAULT 0, "Bombard" INTEGER DEFAULT 0,
  "AntiAirCombat" INTEGER DEFAULT 0, "Domain" TEXT, "Cost" INTEGER, "PurchaseYield" TEXT, "MustPurchase" BOOLEAN DEFAULT 0,
  "Maintenance" INTEGER DEFAULT 0, "StrategicResource" TEXT, "PromotionClass" TEXT, "TraitType" TEXT, "PrereqTech" TEXT,
  "PrereqCivic" TEXT, "PrereqDistrict" TEXT, "ObsoleteTech" TEXT, "ObsoleteCivic" TEXT, "CanTrain" BOOLEAN DEFAULT 1,
  "BuildCharges" INTEGER DEFAULT 0, "SpreadCharges" INTEGER DEFAULT 0, "Description" TEXT, PRIMARY KEY("UnitType"));
CREATE TABLE "UnitReplaces" ("CivUniqueUnitType" TEXT NOT NULL, "ReplacesUnitType" TEXT NOT NULL,
  PRIMARY KEY("CivUniqueUnitType", "ReplacesUnitType"));
CREATE TABLE "UnitUpgrades" ("Unit" TEXT NOT NULL, "UpgradeUnit" TEXT NOT NULL, PRIMARY KEY("Unit"));
CREATE TABLE "Districts" ("DistrictType" TEXT NOT NULL, "Name" TEXT, "PrereqTech" TEXT, "PrereqCivic" TEXT,
  "Description" TEXT, "Cost" INTEGER, "RequiresPopulation" BOOLEAN DEFAULT 1, "NoAdjacentCity" BOOLEAN DEFAULT 0,
  "CostProgressionModel" TEXT DEFAULT 'NO_COST_PROGRESSION', "CostProgressionParam1" INTEGER DEFAULT 0, "TraitType" TEXT,
  "Appeal" INTEGER DEFAULT 0, "Housing" INTEGER DEFAULT 0, "Entertainment" INTEGER DEFAULT 0,
  "OnePerCity" BOOLEAN DEFAULT 1, "Coast" BOOLEAN DEFAULT 0, PRIMARY KEY("DistrictType"));
CREATE TABLE "District_Adjacencies" ("DistrictType" TEXT NOT NULL, "YieldChangeId" TEXT NOT NULL,
  PRIMARY KEY("DistrictType", "YieldChangeId"));
CREATE TABLE "Adjacency_YieldChanges" ("ID" TEXT NOT NULL, "Description" TEXT, "YieldType" TEXT, "YieldChange" INTEGER,
  "TilesRequired" INTEGER DEFAULT 1, "OtherDistrictAdjacent" BOOLEAN DEFAULT 0, "AdjacentSeaResource" BOOLEAN DEFAULT 0,
  "AdjacentTerrain" TEXT, "AdjacentFeature" TEXT, "AdjacentRiver" BOOLEAN DEFAULT 0, "AdjacentWonder" BOOLEAN DEFAULT 0,
  "AdjacentNaturalWonder" BOOLEAN DEFAULT 0, "AdjacentImprovement" TEXT, "AdjacentDistrict" TEXT, "PrereqCivic" TEXT,
  "PrereqTech" TEXT, "ObsoleteCivic" TEXT, "ObsoleteTech" TEXT, "AdjacentResource" BOOLEAN DEFAULT 0,
  "AdjacentResourceClass" TEXT DEFAULT 'NO_RESOURCECLASS', "Self" BOOLEAN DEFAULT 0, PRIMARY KEY("ID"));
CREATE TABLE "Modifiers" ("ModifierId" TEXT NOT NULL, "ModifierType" TEXT NOT NULL, "SubjectRequirementSetId" TEXT,
  PRIMARY KEY("ModifierId"));
CREATE TABLE "DynamicModifiers" ("ModifierType" TEXT NOT NULL, "CollectionType" TEXT, "EffectType" TEXT,
  PRIMARY KEY("ModifierType"));
CREATE TABLE "ModifierArguments" ("ModifierId" TEXT NOT NULL, "Name" TEXT NOT NULL, "Type" TEXT DEFAULT 'ARGTYPE_IDENTITY',
  "Value" TEXT NOT NULL, PRIMARY KEY("ModifierId", "Name"));
CREATE TABLE "ModifierStrings" ("ModifierId" TEXT NOT NULL, "Context" TEXT NOT NULL, "Text" TEXT NOT NULL,
  PRIMARY KEY("ModifierId", "Context"));
CREATE TABLE "GreatPersonClasses" ("GreatPersonClassType" TEXT NOT NULL, "Name" TEXT, "UnitType" TEXT, "DistrictType" TEXT,
  PRIMARY KEY("GreatPersonClassType"));
CREATE TABLE "GreatPersonIndividuals" ("GreatPersonIndividualType" TEXT NOT NULL, "Name" TEXT, "GreatPersonClassType" TEXT,
  "EraType" TEXT, "ActionCharges" INTEGER DEFAULT 0, "ActionRequiresOwnedTile" BOOLEAN DEFAULT 0,
  "ActionRequiresCompletedDistrictType" TEXT, "ActionRequiresGoldCost" INTEGER, "ActionEffectTextOverride" TEXT,
  "BirthEffectTextOverride" TEXT, PRIMARY KEY("GreatPersonIndividualType"));
CREATE TABLE "GreatPersonIndividualActionModifiers" ("GreatPersonIndividualType" TEXT NOT NULL, "ModifierId" TEXT NOT NULL,
  "AttachmentTargetType" TEXT, PRIMARY KEY("GreatPersonIndividualType", "ModifierId"));
