import copy

from career_agent.security.model_view import contact_values, model_view


def test_provider_view_private_resume_and_requirements_are_copy_only():
    private = "林合成 synthetic@example.invalid 13800138000 住址：合成街99号；"
    resume = {
        "profile_id": "profile-ref",
        "template": "resume_zh_cn_a4_single_v1",
        "metadata": {"label": private},
        "sections": [
            {
                "items": [
                    {
                        "text": private + "Python / FastAPI 项目，2025年提升20%。",
                        "fact_refs": ["fact-ref"],
                    }
                ]
            }
        ],
    }
    data = {
        "base_resume": resume,
        "variant": resume,
        "requirements": [
            {"text": private + "PostgreSQL", "evidence_span": private, "id": "requirement-ref"}
        ],
        "company": "上海合成公司",
        "skills": ["Python", "FastAPI"],
        "contact": {"address": "合成街99号"},
    }
    original = copy.deepcopy(data)
    view = model_view(data, name="林合成")
    assert data == original
    for value in ["林合成", "synthetic@example.invalid", "13800138000", "合成街99号"]:
        assert value not in str(view)
    assert "metadata" not in view["variant"]
    for value in [
        "Python",
        "FastAPI",
        "PostgreSQL",
        "2025",
        "20%",
        "上海合成公司",
        "fact-ref",
        "requirement-ref",
        "profile-ref",
    ]:
        assert value in str(view)


def test_known_contact_and_name_boundaries_preserve_business_semantics():
    values = contact_values({"address": "合成街道十号", "location": "上海"})
    view = model_view(
        {"text": "Ann 使用 Annotated 在上海项目开发；合成街道十号"}, name="Ann", contacts=values
    )
    assert "Annotated" in view["text"] and "上海项目开发" in view["text"]
    assert "合成街道十号" not in view["text"]


def test_personal_address_does_not_swallow_following_business_clause():
    value = model_view("地址：合成街99号，Python 项目；公司地址：上海。")
    assert "合成街99号" not in value
    assert "Python 项目" in value and "公司地址：上海" in value
