using FluentAssertions;
using Synapse.Generator.Scanning;
using Synapse.Generator.Tests.Helpers;

namespace Synapse.Generator.Tests.Scanning;

public class FileSystemVaultScannerTests
{
    private readonly FileSystemVaultScanner _scanner = new();

    [Fact]
    public void GetNoteFiles_ReturnsExactlyNineNotes()
    {
        var vaultRoot = FixtureVaultPath.GetPath();

        var files = _scanner.GetNoteFiles(vaultRoot);

        files.Should().HaveCount(9);
    }

    [Fact]
    public void GetNoteFiles_ContainsAllExpectedNoteRelativePaths()
    {
        var vaultRoot = FixtureVaultPath.GetPath();

        var files = _scanner.GetNoteFiles(vaultRoot);
        var relPaths = files
            .Select(f => Path.GetRelativePath(vaultRoot, f).Replace('\\', '/'))
            .ToList();

        relPaths.Should().Contain("docker-basics.md");
        relPaths.Should().Contain("dockerfile.md");
        relPaths.Should().Contain("docker-compose.md");
        relPaths.Should().Contain("docker-networking.md");
        relPaths.Should().Contain("linux-fundamentals.md");
        relPaths.Should().Contain("process-scheduling.md");
        relPaths.Should().Contain("kubernetes-intro.md");
        relPaths.Should().Contain("docker-volumes.md");
        relPaths.Should().Contain("vim-shortcuts.md");
    }

    [Fact]
    public void GetNoteFiles_DoesNotIncludeFilesInHiddenDirectories()
    {
        var vaultRoot = FixtureVaultPath.GetPath();

        var files = _scanner.GetNoteFiles(vaultRoot);
        var relPaths = files.Select(f => Path.GetRelativePath(vaultRoot, f));

        // Materialise before asserting so we don't hit expression-tree optional-arg restrictions.
        var hidden = relPaths
            .Where(p => p.Split(Path.DirectorySeparatorChar).Any(s => s.StartsWith('.')))
            .ToList();

        hidden.Should().BeEmpty("no returned path should be inside a hidden directory");
    }
}
