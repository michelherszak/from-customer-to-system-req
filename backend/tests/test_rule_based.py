from kusys.analysis.rule_based import RuleBasedAnalysisProvider


def test_US13_AC_06_deterministic_requirement_extraction():
    text = "Das System muss sicher sein. Hintergrundinformation. The system should log access."
    result = RuleBasedAnalysisProvider().extract_requirements(text)
    assert [x.priority for x in result] == ["muss", "soll"]
