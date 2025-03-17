import re
from datetime import datetime
import struct
from IPython.display import display
import pandas as pd


class SaveGameEditor:
    def __init__(self, ext=".dat", root_dir=None, campaign=None):
        self.root_dir = root_dir
        self.campaign = campaign
        self.file = f"{self.root_dir}/{self.campaign}/{self.campaign}{ext}"
        self._read_savegame()
        self._save_backup_savegame()
        self._dat_to_json()
        self.scenario_state_dict = {
            0: "None",
            1: "Locked",
            2: "Unlocked",
            3: "InProgress",
            4: "Completed",
            5: "Blocked",
            6: "InProgressCasual",
        }
        self.recordtype_enum = {
            "SerializedStreamHeader": 0,
            "ClassWithId": 1,
            "SystemClassWithMembers": 2,
            "ClassWithMembers": 3,
            "SystemClassWithMembersAndTypes": 4,
            "ClassWithMembersAndTypes": 5,
            "BinaryObjectString": 6,
            "BinaryArray": 7,
            "MemberPrimitiveTyped": 8,
            "MemberReference": 9,
            "ObjectNull": 10,
            "MessageEnd": 11,
            "BinaryLibrary": 12,
            "ObjectNullMultiple256": 13,
            "ObjectNullMultiple": 14,
            "ArraySinglePrimitive": 15,
            "ArraySingleObject": 16,
            "ArraySingleString": 17,
            "ArrayOfType": 18,
            "MethodCall": 19,
            "MethodReturn": 20,
        }

    def _save_backup_savegame(self):
        now_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(f"{self.file}-backup-{now_str}", "wb") as f:
            f.write(self.txt)

    def _read_savegame(self):
        with open(self.file, "rb") as f:
            self.txt = f.read()

    def save_savegame(self):
        with open(self.file, "wb") as f:
            f.write(self.txt)

    def _read_events(self):
        res = re.search(b"(?s)_City_Campaign_[a-zA-Z0-9]*ID(?!.{6}E)", self.txt)
        city_pattern = b"Event_City_Campaign_([a-zA-Z0-9]*)ID"
        self.city_events = [n for n in re.findall(city_pattern, self.txt[: res.span()[1]])]
        self.n_city_events = len(self.city_events)
        res = re.search(b"(?s)_Road_Campaign_[a-zA-Z0-9]*ID(?!.{6}E)", self.txt)
        road_pattern = b"Event_Road_Campaign_([a-zA-Z0-9]*)ID"
        self.road_events = [n for n in re.findall(road_pattern, self.txt[: res.span()[1]])]
        self.n_road_events = len(self.road_events)

    @staticmethod
    def _replace_substring_inplace(txt, substr, span):
        return txt[: span[0]] + substr + txt[span[1] :]

    @staticmethod
    def _prettify_events(events):
        return " ".join([e.decode("utf-8") for e in events])

    def show_events_info(self, event=None):
        self._read_events()
        if event == "city" or event is None:
            print(f"{self.n_city_events} City Events:")
            print(f"Current order: {self._prettify_events(self.city_events)}")
            print(f"Sorted: {self._prettify_events(sorted(self.city_events))}")
        if event is None:
            print("")
        if event == "road" or event is None:
            print(f"{self.n_road_events} Road Events:")
            print(f"Current order: {self._prettify_events(self.road_events)}")
            print(f"Sorted: {self._prettify_events(sorted(self.road_events))}")

    @staticmethod
    def _get_events_span(events_txt, event="city"):
        event_capital = b"City" if event == "city" else b"Road"
        return [
            {"event_number": int(re.search(b"_([0-9]*)ID", e.group()).group(1)), "event_span": e.span()}
            for e in list(re.finditer(b"(\x17|\x18)Event_" + event_capital + b"_Campaign_[a-zA-Z0-9]*ID", events_txt))
        ]

    @staticmethod
    def _next_power_of_2(x, min_power=2):
        return max(2**min_power, 1 if x == 0 else 2 ** (x - 1).bit_length())

    def replace_events(self, event="city", new_events=None, verbose=True):
        event_capital = b"City" if event == "city" else b"Road"
        if not new_events:
            print("You didn't specify new events to replace the existing events with!")
            return

        # Find the location of the event data within the full text
        events_start_index = (
            list(re.finditer(b"Event_" + event_capital + b"_Campaign_[a-zA-Z0-9]*ID", self.txt))[0].start() - 10
        )
        events_end_index = (
            list(
                re.finditer(
                    b"(?s)_Campaign_[a-zA-Z0-9]*ID(?!(\n|\r.)*.{6}E)((?:\n|\r.)*)", self.txt[events_start_index:]
                )
            )[0].end()
            + events_start_index
        )

        # Get first BinaryObjectString object ID
        first_event_object_id = struct.unpack("<I", self.txt[events_start_index + 5 : events_start_index + 9])[0]

        # Number of events submitted
        n_events = len(new_events)

        # Create the new events txt
        # define the length of the array in which to store the events, which should be a power of 2
        array_length = self._next_power_of_2(n_events)  # define the length of the a
        new_events_txt = struct.pack("<I", array_length)  # the length of the array in little endian

        # Create string excluding ID
        event_string_noid = b"Event_" + event_capital + b"_Campaign_"

        # now add the stuff for each event
        for i, new_event in enumerate(new_events):
            # record type 6
            new_events_txt += b"\x06"
            # first BinaryObjectString object ID--applied to every BinaryObjectString in array
            new_events_txt += struct.pack("<I", first_event_object_id + i)
            # the length of the string defining the event
            new_events_txt += len(event_string_noid.decode("utf-8") + str(new_event) + "ID").to_bytes(1, "little")
            new_events_txt += event_string_noid + bytes(str(new_event), "utf-8") + b"ID"
        if array_length - n_events > 1:
            n_nulls = array_length - n_events
            # If there is more than one space left in the array, add a ObjectNullMultiple256 (13 = \r)
            # and the number of nulls to add
            new_events_txt += b"\r" + n_nulls.to_bytes(1, "little")
        elif array_length - n_events == 1:
            # If there is exactly one space left in the array, add a single null (10 = \n)
            new_events_txt += b"\n"
        else:
            # If there are no spaces left in the array, we're finished
            pass

        # Check for discard deck.
        # Next array in save file. Used to find end of discard deck if present.
        next_deck = b"Event_Road_Campaign_" if event == "city" else b"PERSONALQUEST_"

        # Find the possible location of the event discard deck within the full text
        discard_start_index = events_end_index
        discard_end_index = (
            list(re.finditer(next_deck, self.txt[discard_start_index:]))[0].start() - 15 + discard_start_index
        )

        # Test for presence of discard deck (is discard deck between event deck and next deck)
        if discard_start_index != discard_end_index:
            # add empty discard deck
            discard_array_length = struct.unpack("<I", self.txt[discard_start_index + 5 : discard_start_index + 9])[0]
            # array, object ID, array size
            new_events_txt += self.txt[discard_start_index : discard_start_index + 9]
            if discard_array_length > 1:
                # If there is more than one space in the array, add a ObjectNullMultiple256 (13 = \r)
                # and the number of nulls to add
                new_events_txt += b"\r" + discard_array_length.to_bytes(1, "little")
            elif discard_array_length == 1:
                # If there is exactly one space in the array, add a single null (10 = \n)
                new_events_txt += b"\n"
            else:
                # If there are no spaces left in the array, add no nulls. This case should not happen as it would
                # softlock the game.
                pass
        else:
            # If there is no discard deck, we're finished
            pass

        self.txt = self._replace_substring_inplace(self.txt, new_events_txt, (events_start_index, discard_end_index))
        self.show_events_info(event=event)

    def show_character_info(self, characters=None):
        char_info = []
        if characters:
            for char in characters:
                gold, exp, level, perks, checks = self.update_char_values(
                    char_name=char, verbose=False, return_values=True
                )
                char_info.append(
                    {
                        "name": char,
                        "gold": gold,
                        "level": level,
                        "experience": exp,
                        "perk points available": perks,
                        "perk checks": checks,
                    }
                )
        print("\nInfo about current characters:")
        display(pd.DataFrame(char_info).sort_values(by="experience", ascending=False))

    def update_char_values(
        self,
        char_name="Sol Goodman",
        gold=None,
        exp=None,
        perk_points=None,
        perk_checks=None,
        verbose=True,
        return_values=False,
    ):
        char_info_span = re.search(bytes(char_name, "utf-8") + b"(?s:.)*?ID(.*)\n\n", self.txt).span(1)
        gold_span = (char_info_span[0], char_info_span[0] + 4)
        exp_span = (char_info_span[0] + 4, char_info_span[0] + 8)
        level_span = (char_info_span[0] + 8, char_info_span[0] + 12)
        perk_points_span = (char_info_span[1] - 12, char_info_span[1] - 8)
        perk_checks_span = (char_info_span[1] - 8, char_info_span[1] - 4)
        current_gold = struct.unpack("<I", self.txt[gold_span[0] : gold_span[1]])[0]
        current_exp = struct.unpack("<I", self.txt[exp_span[0] : exp_span[1]])[0]
        current_level = struct.unpack("<I", self.txt[level_span[0] : level_span[1]])[0]
        current_perk_points = struct.unpack("<I", self.txt[perk_points_span[0] : perk_points_span[1]])[0]
        current_perk_checks = struct.unpack("<I", self.txt[perk_checks_span[0] : perk_checks_span[1]])[0]
        if gold is not None:
            new_gold_str = struct.pack("<I", gold)
            self.txt = self._replace_substring_inplace(self.txt, new_gold_str, gold_span)
            new_gold = struct.unpack("<I", self.txt[gold_span[0] : gold_span[1]])[0]
            if verbose:
                print(f"{char_name}'s gold amount was updated from {current_gold} to {new_gold}.")
        elif verbose:
            print(f"{char_name} currently has {current_gold} gold.")
        if exp is not None:
            new_exp_str = struct.pack("<I", exp)
            self.txt = self._replace_substring_inplace(self.txt, new_exp_str, exp_span)
            new_exp = struct.unpack("<I", self.txt[exp_span[0] : exp_span[1]])[0]
            if verbose:
                print(f"{char_name}'s experience was updated from {current_exp} (level {current_level}) to {new_exp}.")
        elif verbose:
            print(f"{char_name} currently is level {current_level} with {current_exp} experience.")
        if perk_points is not None:
            new_perks_str = struct.pack("<I", perk_points)
            self.txt = self._replace_substring_inplace(self.txt, new_perks_str, perk_points_span)
            new_perk_points = struct.unpack("<I", self.txt[perk_points_span[0] : perk_points_span[1]])[0]
            if verbose:
                print(
                    f"{char_name}'s available perk points was updated from {current_perk_points} to {new_perk_points}."
                )
        elif verbose:
            print(f"{char_name} currently has {current_perk_points} available perk points.")
        if perk_checks is not None:
            perk_checks_str = struct.pack("<I", perk_checks)
            self.txt = self._replace_substring_inplace(self.txt, perk_checks_str, perk_checks_span)
            new_perk_checks = struct.unpack("<I", self.txt[perk_checks_span[0] : perk_checks_span[1]])[0]
            if verbose:
                print(
                    f"{char_name}'s available perk checks was updated from {current_perk_checks} to {new_perk_checks}."
                )
        elif verbose:
            print(f"{char_name} currently has {current_perk_checks} available perk checks.")
        if return_values:
            return (
                gold or current_gold,
                exp or current_exp,
                current_level,
                perk_points or current_perk_points,
                perk_checks or current_perk_checks,
            )

    def toggle_scenario_status(self, scenario=1, status=None):
        if scenario == 19:
            scenario_span = re.search(
                b"\x12Quest_Campaign_" + bytes(f"{scenario:03d}", "utf-8") + b"(.*?\t.*?)\t", self.txt
            ).span(1)
        else:
            scenario_span = re.search(
                b"\x12Quest_Campaign_" +
                bytes(f"{scenario:03d}", "utf-8") + b"(.*?)\t", self.txt
            ).span(1)
        current_scenario_state = struct.unpack(
            "<I", self.txt[scenario_span[1] - 4: scenario_span[1]])[0]
        if status is not None:
            if self.scenario_state_dict[current_scenario_state] in ("Locked", "Unlocked", "Blocked"):
                new_scenario_state = list(self.scenario_state_dict.keys(
                ))[list(self.scenario_state_dict.values()).index(status)]
                if new_scenario_state is not None:
                    new_scenario_state_str = struct.pack(
                        "<I", new_scenario_state)
                    scenario_state_span = (
                        scenario_span[1] - 4, scenario_span[1])
                    self.txt = self._replace_substring_inplace(
                        self.txt, new_scenario_state_str, scenario_state_span)
                    new_scenario_state = struct.unpack(
                        "<I", self.txt[scenario_span[1] - 4: scenario_span[1]])[0]
                    cur_state = self.scenario_state_dict[current_scenario_state]
                    new_state = self.scenario_state_dict[new_scenario_state]
                    print(
                        f"Scenario {scenario} was changed from {cur_state} to {new_state}.")
            else:
                print(f"Scenario {scenario} is currently {self.scenario_state_dict[current_scenario_state]}.")
                print("I can't change the state of such a scenario.")
        else:
            print(f"Scenario {scenario} is currently {self.scenario_state_dict[current_scenario_state]}.")

    def show_scenario_overview(self, verbose=False):
        scenarios = [m for m in re.finditer(b"\x12Quest_Campaign_([0-9]{3})([\s\S]*?\x00\x00\x00)\t", self.txt)]
        overview = {
            "Completed": [],
            "InProgress": [],
            "InProgressCasual": [],
            "Unlocked": [],
            "Locked": [],
            "Blocked": [],
            "None": [],
        }
        processed_scenarios = []
        for scenario in scenarios:
            scenario_nbr = int(scenario.group(1))
            scenario_state = struct.unpack("<I", scenario.group(2)[-4:])[0]
            if scenario_nbr in processed_scenarios:
                # this scenario was already processed
                pass
            else:
                overview[self.scenario_state_dict[scenario_state]].append(scenario_nbr)
                processed_scenarios.append(scenario_nbr)

        print("\nScenario Overview:")
        for k, v in overview.items():
            if (len(v) > 0 and k != "Locked") or verbose:
                print(f"    {k}: {' '.join([str(s) for s in v])}")

    def show_campaign_info(self):
        self.update_campaign_values()

    def update_campaign_values(self, donated=None, prosperity=None, reputation=None):
        donated_span = re.search(b"GoldDonated", self.txt).span()
        donated_gold_span = (donated_span[1] + 6, donated_span[1] + 10)
        current_gold_donated = struct.unpack("<I", self.txt[donated_gold_span[0] : donated_gold_span[1]])[0]
        if donated is not None:
            new_gold_donated_str = struct.pack("<I", donated)
            self.txt = self._replace_substring_inplace(self.txt, new_gold_donated_str, donated_gold_span)
            print(
                f"The total gold donated to the tree was updated from {current_gold_donated:,}"
                f" gold to {donated} gold."
            )
        else:
            print(f"\nGold donated to the tree so far: {current_gold_donated:,}")

        campaign_span = list(re.finditer(b"MapRuleLibrary\.Party\.CMapCharacter.*?\\t(.*?)\\t", self.txt))[0].span(1)
        prosperity_span = (campaign_span[0] + 4, campaign_span[0] + 8)
        current_prosperity = struct.unpack("<I", self.txt[prosperity_span[0] : prosperity_span[1]])[0]
        if prosperity is not None:
            new_prosperity_str = struct.pack("<I", prosperity)
            self.txt = self._replace_substring_inplace(self.txt, new_prosperity_str, prosperity_span)
            print(f"Prosperity was updated from {current_prosperity} to {prosperity}.")
        else:
            print(f"Current prosperity: {current_prosperity}")

        reputation_span = (campaign_span[0] + 8, campaign_span[1])
        current_reputation = struct.unpack("<I", self.txt[reputation_span[0] : reputation_span[1]])[0]
        if reputation is not None:
            new_reputation_str = struct.pack("<I", reputation)
            self.txt = self._replace_substring_inplace(self.txt, new_reputation_str, reputation_span)
            print(f"Reputation was updated from {current_reputation} to {reputation}.")
        else:
            print(f"Current reputation: {current_reputation}")

    def _dat_to_json(self):
        try:
            import netfleece
        except ModuleNotFoundError:
            raise Exception(
                "You need to install the netfleece package with `pip install netfleece` to use this method."
            )
        except Exception:
            raise Exception(
                "A required package (netfleece) could not be imported.\nThis package unfortunately doesn't "
                "work in Python 3.9 and above.\nPlease try again in a Python 3.8 environment!"
            )
        with open(self.file, "rb") as infile:
            self.json = netfleece.parseloop(infile)

    def show_personal_quests(self):
        self.prioritise_personal_quests()

    def remove_personal_quests(self, quests_to_remove=None):
        if quests_to_remove is None:
            self.show_personal_quests()
            return
        quests_dict, pq_deck_obj_str, pq_deck_span, pq_deck_str = self._read_personal_quest_deck()
        quests_to_remove_bytes = [str.encode(s) for s in quests_to_remove]
        for quest in quests_to_remove_bytes:
            if quest in quests_dict.keys():
                quests_dict.pop(quest)
            else:
                print(f"Quest {quest.decode('utf-8')} was not found in the quest deck!")
        self._recreate_personal_quest_deck(quests_dict, pq_deck_obj_str, pq_deck_span)

    def _read_personal_quest_deck(self):
        pq_deck_path = self._get_paths_to_value(self.json, "PersonalQuestDeck")[0]
        pq_deck_idref1 = self.json[pq_deck_path[0]][pq_deck_path[1]]["Values"][pq_deck_path[4]]["IdRef"]
        pq_deck_idref2 = self._get_obj_value(self.json, pq_deck_idref1)["Values"][0]["IdRef"]
        pq_deck_objectid = self._get_obj_value(self.json, pq_deck_idref2)["Values"][0]["IdRef"]
        pq_deck_recordtype = self.recordtype_enum[self._get_obj_value(self.json, pq_deck_objectid)["RecordTypeEnum"]]
        pq_deck_obj_str = pq_deck_recordtype.to_bytes(1, "little") + struct.pack("<I", pq_deck_objectid)
        pq_deck_span = re.search(pq_deck_obj_str + b".{4}(\x06.{5}[A-Za-z_]*)*(\\n|\\r.)?", self.txt).span()
        pq_deck_str = self.txt[pq_deck_span[0] : pq_deck_span[1]]
        quests = list(re.finditer(b"(\x06.{4}.(PERSONALQUEST|PersonalQuest).*?)(?=\x06|$|\\n|\\r)", pq_deck_str))
        quests_dict = {
            quest.group()[20:]: {
                "object_id": quest.group()[1:5],
                "length": len(quest.group()[6:]),
                "quest_str": quest.group()[6:],
            }
            for quest in quests
        }
        return quests_dict, pq_deck_obj_str, pq_deck_span, pq_deck_str

    def _recreate_personal_quest_deck(self, quests_dict, pq_deck_obj_str, pq_deck_span):
        deck_length = 25
        new_pq_deck_str = pq_deck_obj_str + struct.pack("<I", deck_length)
        for quest, quest_info in quests_dict.items():
            new_pq_deck_str += (
                b"\x06" + quest_info["object_id"] + quest_info["length"].to_bytes(1, "little") + quest_info["quest_str"]
            )
        nulls_to_add = deck_length - len(quests_dict)
        if nulls_to_add < 0:
            raise Exception("There are more quests in the deck than allowed!")
        elif nulls_to_add == 0:
            pass
        elif nulls_to_add == 1:
            new_pq_deck_str += self.recordtype_enum["ObjectNull"].to_bytes(1, "little")
        elif nulls_to_add > 1:
            new_pq_deck_str += self.recordtype_enum["ObjectNullMultiple256"].to_bytes(
                1, "little"
            ) + nulls_to_add.to_bytes(1, "little")
        self.txt = self._replace_substring_inplace(self.txt, new_pq_deck_str, pq_deck_span)
        print("New personal quest deck order:")
        for quest in quests_dict:
            print(f"    {quest.decode('utf-8')}")

    def prioritise_personal_quests(self, prioritize=None):
        quests_dict, pq_deck_obj_str, pq_deck_span, pq_deck_str = self._read_personal_quest_deck()
        if prioritize is None:
            print("\nCurrent personal quest deck order:")
            for quest, _ in quests_dict.items():
                print(f"    {quest.decode('utf-8')}")
            return

        prioritize_bytes = [str.encode(s) for s in prioritize]
        current_order = list(quests_dict.keys())
        new_order = []
        for quest in prioritize_bytes:
            if quest in current_order:
                current_order.remove(quest)
            else:
                raise Exception(f"The quest '{quest.decode('utf-8')}' isn't currently in the deck! Maybe a typo?")
            new_order.append(current_order.pop(0))
            new_order.append(quest)
        new_order.extend(current_order)
        quests_dict = {quest: quests_dict[quest] for quest in new_order}
        self._recreate_personal_quest_deck(quests_dict, pq_deck_obj_str, pq_deck_span)

    def _read_chest_deck(self):
        self._get_paths_to_value(self.json, "AlreadyRewardedChestTreasureTableIDs")
        chests_path = self._get_paths_to_value(self.json, "AlreadyRewardedChestTreasureTableIDs")[0]
        chests_idref = self.json[chests_path[0]][chests_path[1]]["Values"][chests_path[4]]["IdRef"]
        chests_objectid = self._get_obj_value(self.json, chests_idref)["Values"][0]["IdRef"]
        chests_recordtype = self.recordtype_enum[self._get_obj_value(self.json, chests_objectid)["RecordTypeEnum"]]
        chests_obj_str = chests_recordtype.to_bytes(1, "little") + struct.pack("<I", chests_objectid)
        chests_span = re.search(chests_obj_str + b".{4}(\x06.{5}[A-Za-z_0-9]*)*(\\n|\\r.)?", self.txt).span()
        chests_deck_str = self.txt[chests_span[0]: chests_span[1]]
        chests_looted = list(re.finditer(b"\x06(.{4}).TT_Campaign_Chest_([0-9]{2})(?=\x06|$|\\n|\\r)", chests_deck_str))
        chests_dict = {int(chest.group(2)): chest.group(1) for chest in chests_looted}
        return chests_dict, chests_obj_str, chests_span, chests_deck_str

    def show_looted_chests(self):
        chests_dict, chests_obj_str, chests_span, chests_deck_str = self._read_chest_deck()
        looted_chests = [int(chest) for chest in list(chests_dict.keys())]
        print(f"\nLooted chests: {' '.join([str(c) for c in looted_chests])}")

    def toggle_chests(self, looted=None):
        chests_dict, chests_obj_str, chests_span, chests_deck_str = self._read_chest_deck()
        current_looted_chests = [int(chest) for chest in list(chests_dict.keys())]
        first_chest_object_id = 3000000 # struct.unpack("<I", chests_dict[current_looted_chests[0]])[0]
        new_looted_chests = sorted(set(current_looted_chests).union(set(looted)))
        chests_to_be_looted = sorted(set(new_looted_chests).difference(set(current_looted_chests)))
        print(f"The following chests will now be set to 'looted': {' '.join(str(c) for c in chests_to_be_looted)}")
        chest_deck_length = self._next_power_of_2(len(new_looted_chests))
        new_chests_deck_str = chests_obj_str + struct.pack("<I", chest_deck_length)
        chest_str_length = 20
        for i, chest in enumerate(new_looted_chests):
            new_chests_deck_str += b"\x06" + struct.pack("<I", first_chest_object_id + i)
            new_chests_deck_str += chest_str_length.to_bytes(1, "little")
            new_chests_deck_str += b"TT_Campaign_Chest_" + bytes(str(chest).zfill(2), "utf-8")
        nulls_to_add = chest_deck_length - len(new_looted_chests)
        if nulls_to_add < 0:
            raise Exception("There are more quests in the deck than allowed!")
        elif nulls_to_add == 0:
            pass
        elif nulls_to_add == 1:
            new_chests_deck_str += self.recordtype_enum["ObjectNull"].to_bytes(1, "little")
        elif nulls_to_add > 1:
            new_chests_deck_str += self.recordtype_enum["ObjectNullMultiple256"].to_bytes(
                1, "little"
            ) + nulls_to_add.to_bytes(1, "little")
        self.txt = self._replace_substring_inplace(self.txt, new_chests_deck_str, chests_span)
        self.show_looted_chests()

    def _breadcrumb_finder(self, json_dict_or_list, value, path, result):
        """
        This recursive function is able to parse through a nested JSON dictionary or list to find all occurences of
        a given value and return their "paths" in the JSON object
        See https://stackoverflow.com/a/69537980/3112000
        :param json_dict_or_list: JSON dict or list to parse through
        :param value: value that we're looking for
        :param path: current path that we're looking at
        :param result: list of all the paths found so far
        :return: nothing as the results list is edited in-place
        """
        if json_dict_or_list == value:
            path.append(json_dict_or_list)
            result.append(path.copy())
            path.pop()
        elif isinstance(json_dict_or_list, dict):
            for k, v in json_dict_or_list.items():
                path.append(k)
                self._breadcrumb_finder(v, value, path, result)
                path.pop()

        elif isinstance(json_dict_or_list, list):
            lst = json_dict_or_list
            for i in range(len(lst)):
                path.append(i)
                self._breadcrumb_finder(lst[i], value, path, result)
                path.pop()

    def _get_paths_to_value(self, data, value):
        results = []
        self._breadcrumb_finder(data, value, [], results)
        return results

    def _get_paths_to_key_value(self, data, key, value):
        results = []
        self._breadcrumb_finder(data, value, [], results)
        return [r for r in results if r[-2:] == [key, value]]

    def _get_obj_value(self, data, objectid):
        path = self._get_paths_to_key_value(data, "ObjectId", objectid)[0]
        return data[path[0]][path[1]]

    # TODO:
    # * method to change character's name
    # * method to respec a character's ability cards (https://docs.google.com/spreadsheets/d/1ZNVpFGDavZQ7kIHGzodXDLw-xSRCiabz1FkoJ-Aoqc0/edit#gid=1707295556)
    # * method to show a character's available abilities and selected abilities
    # * method to complete a quest with the relevant characters
