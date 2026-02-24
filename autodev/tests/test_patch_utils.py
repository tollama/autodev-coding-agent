from autodev.patch_utils import parse_unified_diff, validate_unified_diff


def test_validate_unified_diff_accepts_markdown_fenced_patch():
    fenced = """```diff
@@ -1,1 +1,1
-foo
+bar
```"""
    validate_unified_diff(fenced)
    hunks = parse_unified_diff(fenced)
    assert len(hunks) == 1
    assert hunks[0].orig_start == 1
    assert hunks[0].orig_len == 1
