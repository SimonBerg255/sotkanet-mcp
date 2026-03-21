"""
Live functional tests. Every test hits the real Sotkanet API.
Exit 0 = all pass. Exit 1 = failures remain.
"""
import asyncio
import sys
import time


async def run_tests():
    failures = []

    # --- TEST 1: Cache warm + search ---
    print("=== TEST 1: Cache warm and indicator search ===")
    try:
        from tools_sotkanet import search_indicators
        result = await search_indicators("elderly care", lang="en")
        assert "id" in result.lower() or "indicator" in result.lower(), \
            f"Expected indicator results: {result[:300]}"
        assert len(result) > 100
        print(f"PASS — search returned results\nPreview: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 1: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(0.5)

    # --- TEST 2: Context overflow guard ---
    print("=== TEST 2: Data response must be under 30KB ===")
    try:
        from tools_sotkanet import get_indicator_data
        result = await get_indicator_data(
            indicator_id=127,
            year=2022,
            region_category="HYVINVOINTIALUE"
        )
        char_count = len(result)
        assert char_count < 30_000, \
            f"CONTEXT OVERFLOW: {char_count} chars returned (max 30000)"
        print(f"PASS — {char_count} chars (within limit)\nPreview: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 2: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(0.5)

    # --- TEST 3: KUNTA guard (300 municipalities must be capped) ---
    print("=== TEST 3: Municipality data must be capped ===")
    try:
        from tools_sotkanet import get_indicator_data
        result = await get_indicator_data(
            indicator_id=127,
            year=2022,
            region_category="KUNTA"
        )
        assert len(result) < 40_000, \
            f"Municipality data overflow: {len(result)} chars"
        assert "warning" in result.lower() or "⚠️" in result or "showing" in result.lower(), \
            "Expected a cap warning when returning municipality data"
        print(f"PASS — capped with warning ({len(result)} chars)\n")
    except Exception as e:
        failures.append(f"TEST 3: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(0.5)

    # --- TEST 4: compare_regions returns ranked output ---
    print("=== TEST 4: compare_regions — ranked output ===")
    try:
        from tools_sotkanet import compare_regions
        result = await compare_regions(
            indicator_id=127,
            year=2022,
            region_category="HYVINVOINTIALUE",
            top_n=10,
            sort_order="desc"
        )
        assert len(result) > 100
        assert any(c.isdigit() for c in result), "Expected numeric values"
        assert "average" in result.lower() or "summary" in result.lower(), \
            "Expected summary statistics"
        print(f"PASS\nPreview: {result[:400]}\n")
    except Exception as e:
        failures.append(f"TEST 4: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(0.5)

    # --- TEST 5: get_trend returns time series ---
    print("=== TEST 5: get_trend for one region over time ===")
    try:
        from tools_sotkanet import get_trend
        # Region 658 = Finland (whole country), indicator 127 = population
        result = await get_trend(
            indicator_id=127,
            region_id=658,
            start_year=2018,
            end_year=2022
        )
        assert "2018" in result and "2022" in result, \
            f"Expected year range in output: {result[:300]}"
        print(f"PASS\nPreview: {result[:400]}\n")
    except Exception as e:
        failures.append(f"TEST 5: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(0.5)

    # --- TEST 6: Metadata fetch ---
    print("=== TEST 6: get_indicator_metadata ===")
    try:
        from tools_sotkanet import get_indicator_metadata
        result = await get_indicator_metadata(127)
        assert "population" in result.lower() or "väestö" in result.lower() or "befolkning" in result.lower(), \
            f"Expected population description: {result[:300]}"
        assert "1990" in result or "range" in result.lower() or "available years" in result.lower(), \
            f"Expected year range: {result[:300]}"
        print(f"PASS\nPreview: {result[:400]}\n")
    except Exception as e:
        failures.append(f"TEST 6: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(0.5)

    # --- TEST 7: Timing test ---
    print("=== TEST 7: Timing test — data call must complete in < 30s ===")
    try:
        import time as t
        from tools_sotkanet import get_indicator_data
        start = t.time()
        result = await get_indicator_data(127, 2022, "HYVINVOINTIALUE")
        elapsed = t.time() - start
        assert elapsed < 30, f"Too slow: {elapsed:.1f}s (max 30s)"
        print(f"PASS — {elapsed:.1f}s\n")
    except Exception as e:
        failures.append(f"TEST 7: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(0.5)

    # --- TEST 8: Finnish-language search ---
    print("=== TEST 8: Finnish language search ===")
    try:
        from tools_sotkanet import search_indicators
        result = await search_indicators("väestö", lang="fi")
        assert "id" in result.lower() or "indicator" in result.lower(), \
            f"Expected Finnish indicator results: {result[:300]}"
        print(f"PASS\nPreview: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 8: {e}")
        print(f"FAIL: {e}\n")

    # --- Summary ---
    print("=" * 50)
    if failures:
        print(f"\n❌ {len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n✅ ALL 8 TESTS PASSED — Sotkanet MCP ready")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_tests())
