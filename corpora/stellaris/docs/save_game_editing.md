# Save-game editing
Source: https://stellaris.paradoxwikis.com/Save-game_editing
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20240628013903 (the live wiki blocks non-browser clients)._

and should be accurate for any version of the game.

This article details Stellaris save game format and how to edit them. As a reminder, always make a backup copy of your save file before editing!

## Location (Steam Version)

| OS | Location |
|---|---|
| Windows auto saves (including ironman saves) | \Steam\userdata\%STEAMUSERID%\281990\remote\save games\$EMPIRENAME+ID\ |
| Windows custom saves | %USERPROFILE%\Documents\Paradox Interactive\Stellaris\save games\$EMPIRENAME+ID\ |
| Mac | $HOME/Documents/Paradox Interactive/Stellaris/save games/$EMPIRENAME+ID |
| Linux | $HOME/.local/share/Paradox Interactive/Stellaris/save games/$EMPIRENAME+ID ($XDG_DATA_HOME is ignored!) |
| Linux (newer versions) | $STEAMFOLDER/userdata/$STEAMID/281990/remote/save games/$EMPIRENAME+ID |

Cloud saves can be edited.

Here are the cloud saves locations:

| OS | Location |
|---|---|
| Mac | ~/Library/Application Support/Steam/userdata/<YOUR STEAM ID>/281990/remote/save games/​ |

## Location (Paradox Launcher Version)

| OS | Location |
|---|---|
| Windows | %USERPROFILE%\Documents\Paradox Interactive\Stellaris Plaza\save games\$EMPIRENAME+ID\ |
| Mac | ??? |
| Linux | $HOME/.local/share/Paradox Interactive/Stellaris Plaza/save games/$EMPIRENAME+ID ($XDG_DATA_HOME is ignored!) |

## Location (GamePass Launcher Version)

| OS | Location |
|---|---|
| Windows | %USERPROFILE%\Documents\Paradox Interactive\Stellaris GamePass\save games\$EMPIRENAME+ID\ |

## Format

Each.sav file is a ZIP archive containing two text files: gamestate and meta. They include all the game state data and the meta-information that is shown on the load game screen.

The game seems to be unusually picky about the format when loading:

- The files within the ZIP archive must use UNIX-style newlines. Windows Notepad will not save the newlines correctly, so another editor such as Notepad++ must be used.
- The files within the ZIP archive must have correct timestamps. See OS-specific instructions below.
- When zipping the files, you should select the two text files and create a new.sav archive from those files. If you try to zip the folder containing the edited files, you will get a broken save error when trying to load the game. Move the new.sav into the main save folder

### Compression on Windows

Options for 7-Zip

Use 7-Zip with the following options:

- Archive format: zip
- Compression speed: Fast
- Compression method: Deflate
- Do not include NTFS timestamps (tc=off parameters in bottom left of 7-Zip, or use a version equal to 9.12 beta or earlier)

Do not use WinRAR as it messes compressed lines.

By using the edit function in the 7zip file manager (the editor needs to be chosen by going to tools then options then editor and putting a link to editor of chice) the file can be edited and then once the file is closed 7zip will automatically re-compress the file to ensure no issues

### Compression on Linux or macOS

Use Apple's Archive Utility app to unzip the.sav game file. To do that:

Navigate and select Archive Utility app

```
1. Right-click the .sav file and click Open With > Other...
2. Navigate to: <computer_name>/System/Library/ CoreServices/Applications
3. In the Choose Application dialog change Enable option to All Applications
4. Select the Archive Utility, then click Open
```

A folder appears with the same name as the.sav file containing the gamestate and meta files. Edit using any text editor able to save in Unix LF format.

Put the save back together using:

```
   zip -X output.sav gamestate meta
```

The -X flag is needed to "eXclude eXtra file attributes".

Alternatively, run this Python script from the directory containing the gamestate and meta files.

An easier way to compress the saves on Mac is to highlight the two files, left click and click "Compress 2 Items". A.zip file named Archive.zip will appear: left click on this and click "Get Info". Under the "Name & Extension" section, click the box containing Archive.sav and change.zip to.sav. You will be prompted for confirmation on changing the extension.

## Save Attributes

### gamestate File Details

Nearly any information about a given playthrough can be modified via editing the gamestate file. This includes current energy, mineral, food and unity stores, as well as planet tiles and pop traits. The following is an example of a populated tile on a Fallen Empire's planet, containing a dark matter power plant.

0={ active=yes pop=127 resources={ minerals={1.000 1.000 0.000} } building={ type="building_dark_matter_power_plant" modifier=yes } deposit="d_mineral_deposit")

Modding

| Empire | Empire • Ethics • Governments • Civics • Origins • Mandates • Agendas • Traditions • Ascension perks • Edicts • Policies • Relics • Technologies • Custom empires |
|---|---|

| Pops | Jobs • Factions |
|---|---|

| Leaders | Leaders • Leader traits |
|---|---|

| Species | Species • Species traits |
|---|---|

| Planets | Planets • Planetary feature • Orbital deposit • Buildings • Districts • Planetary decisions |
|---|---|

| Systems | Systems • Starbases • Megastructures • Bypasses • Map |
|---|---|

| Fleets | Fleets • Ships • Components |
|---|---|

| Land warfare | Armies • Bombardment stance |
|---|---|

| Diplomacy | Diplomacy • Federations • Galactic community • Opinion modifiers • Casus Belli • War goals |
|---|---|

| Events | Events • Anomalies • Special projects • Archaeological sites |
|---|---|

| Gameplay | Gameplay • Defines • Resources • Economy • Game start |
|---|---|

| Dynamic modding | Dynamic modding • Effects • Conditions • Scopes • Modifiers • Variables • AI • On actions |
|---|---|

| Media/localisation | Maya exporter • Portraits • Flags • Event pictures • Interface • Icons • Music • Localisation |
|---|---|

| Other | Console commands • Save-game editing • Steam Workshop • Modding tutorial |
|---|---|

NewPP limit report Cached time: 20240628013903 Cache expiry: 86400 Reduced expiry: false Complications: [show‐toc] CPU time usage: 0.046 seconds Real time usage: 0.075 seconds Preprocessor visited node count: 175/1000000 Post‐expand include size: 18184/2097152 bytes Template argument size: 7951/2097152 bytes Highest expansion depth: 7/100 Expensive parser function count: 0/100 Unstrip recursion depth: 0/20 Unstrip post‐expand size: 0/5000000 bytes

Transclusion expansion time report (%,ms,calls,template) 100.00% 36.889 1 -total 55.72% 20.555 1 Template:ModdingNavbox 43.91% 16.197 1 Template:Version 40.83% 15.062 1 Template:Navbox 25.93% 9.564 1 Template:Infobox 13.37% 4.933 14 Template:Navboxgroup 13.05% 4.814 1 Template:Nowrap 12.03% 4.437 1 Template:Clear

Saved in parser cache with key wiki_stellaris-mwstella_:pcache:idhash:1548-0!canonical and timestamp 20240628013903 and revision id 80901.
