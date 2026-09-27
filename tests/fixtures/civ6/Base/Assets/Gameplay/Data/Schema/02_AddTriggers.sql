-- The game hashes Types here; the fixture only checks that the function exists.
CREATE TABLE "TypeHashes" ("Type" TEXT NOT NULL, "Hash" INTEGER);
CREATE TRIGGER "OnTypeInsert" AFTER INSERT ON "Types" BEGIN
  INSERT INTO "TypeHashes" ("Type", "Hash") VALUES (New.Type, Make_Hash(New.Type));
END;
