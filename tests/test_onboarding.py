from genesis_core.onboarding import recommend_models, resource_profile


GIB = 1024 ** 3


def test_recommendations_are_conservative_for_low_memory():
    suggestions = recommend_models(4 * GIB, 1 * GIB)
    assert suggestions[0]["name"] == "gemma3:1b"
    assert suggestions[0]["warning"] is not None
    assert suggestions[0]["estimated_runtime_gb"] > suggestions[0]["download_gb"]


def test_recommendations_scale_with_memory():
    assert recommend_models(8 * GIB)[0]["name"] == "llama3.2:3b"
    assert recommend_models(16 * GIB)[0]["name"] == "gemma3:4b"


def test_resource_profile_flags_low_cpu_even_with_more_ram():
    profile = resource_profile({
        "memory_total_bytes": 8 * GIB, "memory_available_bytes": 5 * GIB,
        "cpu_logical": 2, "disk_free_bytes": 20 * GIB,
    })
    assert profile["tier"] == "limited"
    assert profile["notes"]


def test_resource_profile_handles_unknown_hardware():
    profile = resource_profile({})
    assert profile["tier"] == "unknown"
    assert profile["memory_total_gb"] is None


def test_resource_profile_warns_about_low_disk():
    profile = resource_profile({
        "memory_total_bytes": 16 * GIB, "memory_available_bytes": 12 * GIB,
        "cpu_logical": 8, "disk_free_bytes": GIB,
    })
    assert any("disque" in note for note in profile["notes"])
