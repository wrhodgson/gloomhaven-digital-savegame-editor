from savegame_editor import SaveGameEditor
import json

editor = SaveGameEditor(
    root_dir="./", campaign="Campaign_Bangbang_We're_Dead_1054108285")

campaignJson = open("campaign.json")
campaignData = json.load(campaignJson)

editor.update_campaign_values(
    donated=campaignData["GoldDonations"], prosperity=campaignData["Prosperity"], reputation=campaignData["Reputation"])

editor.replace_events("city", campaignData["CityEvents"], True)
editor.replace_events("road", campaignData["RoadEvents"], True)

editor.toggle_chests(campaignData["LootedChests"])

for character in campaignData["Characters"]:
    editor.update_char_values(character["Name"], character["Gold"], character["Experience"],
                              character["PerkPoints"], character["PerkChecks"], True, False)

for scenario in campaignData["Scenarios"]:
    editor.toggle_scenario_status(scenario["Id"], scenario["Status"])

editor.save_savegame()
