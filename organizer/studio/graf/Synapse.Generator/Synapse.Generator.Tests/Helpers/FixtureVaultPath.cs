namespace Synapse.Generator.Tests.Helpers;

/// <summary>
/// Resolves the path to the fixture vault on disk.
/// The assembly runs from bin/Debug/net8.0; we navigate up three levels to reach the
/// Synapse.Generator.Tests project root, then down into Fixtures/Vault/.
/// </summary>
internal static class FixtureVaultPath
{
    private static string? _cachedPath;

    public static string GetPath()
    {
        if (_cachedPath is not null)
            return _cachedPath;

        var assemblyDir = Path.GetDirectoryName(typeof(FixtureVaultPath).Assembly.Location)!;
        // bin/Debug/net8.0  →  ../../../  →  Synapse.Generator.Tests/
        var projectDir = Path.GetFullPath(Path.Combine(assemblyDir, "..", "..", ".."));
        _cachedPath = Path.Combine(projectDir, "Fixtures", "Vault");
        return _cachedPath;
    }

    public static string GetFilePath(string fileName) =>
        Path.Combine(GetPath(), fileName);
}
