"""No UI runner. Tests our state and the shipped extensions repo's widget-schema mirror."""
import unittest
from panel_logic import Panel
from schema import check

class FilterPanelTests(unittest.TestCase):
    def valid(self, state):
        root = state.root()
        check(self, root)
        return root["children"]

    def test_initial_filter_no_matches_clear(self):
        state=Panel()
        toolbar, results = self.valid(state)
        self.assertEqual(len(results["rows"]), 3)
        initial=toolbar["children"][0]
        self.assertEqual((initial["id"], initial["action"], initial["value"]), ("name-filter","filter",""))
        state=state.apply("filter"," ЛИП ")
        toolbar,results=self.valid(state)
        self.assertEqual([r[0] for r in results["rows"]], ["Заметка о липе","Липовый чай"])
        widget=toolbar["children"][0]
        self.assertEqual((widget["id"],widget["action"],widget["value"]),("name-filter","filter"," ЛИП "))
        state=state.apply("filter","Берёза")
        _,empty=self.valid(state)
        self.assertEqual(empty,{"type":"text","text":"Совпадений нет"})
        state=state.apply("filter","")
        self.assertEqual(len(self.valid(state)[1]["rows"]),3)

    def test_view_local_state_does_not_leak(self):
        panels={"view-A":Panel(),"view-B":Panel()}
        for view,value in [("view-A","чай"),("view-B","покуп"),("view-B","")]:
            panels[view]=panels[view].apply("filter",value)
        self.assertEqual(self.valid(panels["view-A"])[1]["rows"], [["Липовый чай","Готово"]])
        self.assertEqual(len(self.valid(panels["view-B"])[1]["rows"]),3)

    def test_unknown_or_bad_action_keeps_state(self):
        state=Panel("чай")
        for action,value in [("filter",None),("else","")]:
            self.assertEqual(state.apply(action,value),state)
        self.valid(state)

    def test_typo_in_field_is_detected_by_upstream_mirror(self):
        root=Panel().root()
        root["children"][0]["children"][0]["placeHolder"]="Название"
        with self.assertRaises(AssertionError): check(self,root)

    def test_multiline_search_is_rejected_by_upstream_mirror(self):
        root=Panel().root()
        root["children"][0]["children"][0]["lines"]=2
        with self.assertRaises(AssertionError): check(self,root)

if __name__ == "__main__":
    unittest.main()
