"""Runtime configuration ownership and effective-contract tests."""
from app.core.config import Settings
from app.services.config_service import ConfigService
from app.tests._service_harness import FakeLogger


def test_answer_evaluation_defaults_to_json_schema():
    settings = Settings(_env_file=None)

    assert settings.answer_evaluation_structured_output_transport == "json_schema"


def test_effective_config_is_read_only_and_omits_secrets():
    settings = Settings(
        _env_file=None,
        llm_implementation="vllm",
        vllm_api_key="do-not-expose",
        default_model="demo",
        rag_chat_model="demo",
    )

    effective = ConfigService(FakeLogger(), settings).get_config()

    assert effective["configuration_policy"]["owner"] == "deployment"
    assert effective["configuration_policy"]["live_effective"] == []
    assert "vllm_api_key" not in effective
    assert not hasattr(ConfigService, "update_config")
