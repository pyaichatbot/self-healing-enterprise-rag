from shrag.eval.golden import GoldenCase, pass_golden


def test_golden_eval_matches_expected_keyword():
    case = GoldenCase(case_id="g1", query="What is RAG?", expected_substring="retrieval")
    assert pass_golden("This answer explains retrieval augmented generation.", case) is True
    assert pass_golden("This answer is unrelated.", case) is False
