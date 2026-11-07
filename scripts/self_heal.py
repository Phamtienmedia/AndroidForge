REPO_ROOT = Path(__file__).resolve().parent.parent


# Minimum APP_PLATFORM (android-NN) required by each NDK major version.
# NDK r21 allows android-19; r23+ requires android-21+.
# Below the floor, ndk-build aborts with:
#   "Android NDK: APP_PLATFORM android-19 is lower than minimum supported..."
NDK_MIN_APP_PLATFORM = {
    21: 19,
    23: 21,
    25: 21,
    26: 21,
    27: 21,
}


def _ndk_major(ndk_version: str) -> int:
    """Extract major from '25.2.9519653' → 25. Falls back to 21 on parse error."""
    try:
        return int(str(ndk_version).split(".")[0])
    except (ValueError, AttributeError, IndexError):
        return 21
