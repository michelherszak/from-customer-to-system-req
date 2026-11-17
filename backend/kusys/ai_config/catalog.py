"""Curated cloud models; endpoints and CrewAI provider prefixes stay server-side."""
CATALOG = [
    {"id": "openai/gpt-5.4-mini", "provider": "openai", "provider_label": "OpenAI", "model": "gpt-5.4-mini", "label": "GPT-5.4 mini", "endpoint": "https://api.openai.com/v1"},
    {"id": "openai/gpt-5.4", "provider": "openai", "provider_label": "OpenAI", "model": "gpt-5.4", "label": "GPT-5.4", "endpoint": "https://api.openai.com/v1"},
    {"id": "anthropic/claude-sonnet-5-5", "provider": "anthropic", "provider_label": "Anthropic", "model": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "endpoint": "https://api.anthropic.com"},
    {"id": "anthropic/claude-opus-5-5", "provider": "anthropic", "provider_label": "Anthropic", "model": "claude-opus-5-5", "label": "Claude Opus 5.5", "endpoint": "https://api.anthropic.com"},
    {"id": "anthropic/claude-haiku-5-5", "provider": "anthropic", "provider_label": "Anthropic", "model": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "endpoint": "https://api.anthropic.com"},
    {"id": "anthropic/claude-sonnet-4-6", "provider": "anthropic", "provider_label": "Anthropic", "model": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "endpoint": "https://api.anthropic.com"},
    {"id": "gemini/gemini-3.8-flash", "provider": "gemini", "provider_label": "Google", "model": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "endpoint": "https://generativelanguage.googleapis.com/v1beta"},
    {"id": "gemini/gemini-3.6-flash", "provider": "gemini", "provider_label": "Google", "model": "gemini-3.6-flash", "label": "Gemini 3.6 Flash", "endpoint": "https://generativelanguage.googleapis.com/v1beta"},
    {"id": "gemini/gemini-4-hydrogen", "provider": "gemini", "provider_label": "Google", "model": "gemini-4-hydrogen", "label": "Gemini 4 Hydrogen", "endpoint": "https://generativelanguage.googleapis.com/v1beta"},
    {"id": "gemini/gemini-4-argon", "provider": "gemini", "provider_label": "Google", "model": "gemini-4-argon", "label": "Gemini 4 Argon", "endpoint": "https://generativelanguage.googleapis.com/v1beta"},
    {"id": "gemini/gemini-4-carbon", "provider": "gemini", "provider_label": "Google", "model": "gemini-4-carbon", "label": "Gemini 4 Carbon", "endpoint": "https://generativelanguage.googleapis.com/v1beta"},
]


def selected_model(model_id):
    return next((x for x in CATALOG if x["id"] == model_id), None)
