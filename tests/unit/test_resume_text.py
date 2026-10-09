import pytest

from career_agent.resume.pdf import retained_text_present


@pytest.mark.parametrize(
    "actual,expected,accepted",
    [
        (
            "Alex Skills PySummarython Summary X",
            ["Alex", "Skills", "Python", "Summary", "X"],
            False,
        ),
        (
            "Alex Skills PySummarython Summary X",
            ["Alex", "Skills", "Summary", "Python", "X"],
            False,
        ),
        ("Summary A Summary B", ["Summary", "A", "Summary", "B"], True),
        ("Summary A B", ["Summary", "A", "Summary", "B"], False),
        ("Skills Python Python", ["Skills", "Python", "Python"], True),
        ("Skills Python", ["Skills", "Python", "Python"], False),
        ("Skills Summary X", ["Skills", "Python", "Summary", "X"], False),
        ("Skills Skills", ["Skills", "Skills"], True),
        ("Skills", ["Skills", "Skills"], False),
        ("Skills Skills and tests Summary X", ["Skills", "Skills and tests", "Summary", "X"], True),
        (
            "Skills Built Summary services Summary X",
            ["Skills", "Built Summary services", "Summary", "X"],
            True,
        ),
        (
            "个人简介 中文项目经历 项目经历 模拟服务",
            ["个人简介", "中文项目经历", "项目经历", "模拟服务"],
            True,
        ),
        (
            "项目经历 使用 Python / FastAPI，提升 25%。",
            ["项目经历", "使用 Python/FastAPI，提升 25%。"],
            True,
        ),
        ("技术栈 ＡＢＣ １２３，cafe\u0301", ["技术栈", "ABC 123,café"], True),
        ("项目经历 数项目经历据 项目经历", ["项目经历", "数据", "项目经历"], False),
    ],
)
def test_retained_text_ranges(actual, expected, accepted):
    assert retained_text_present(actual, expected) is accepted
