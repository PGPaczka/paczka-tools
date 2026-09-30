using System.Text.RegularExpressions;
using FluentAssertions;
using Synapse.Generator.Git;
using Synapse.Generator.Tests.Helpers;

namespace Synapse.Generator.Tests.Git;

/// <summary>
/// Integration tests that shell out to git, against a repository the test owns.
///
/// These deliberately assert the CONTRACT (dates exist, are ISO yyyy-mm-dd, oldest first)
/// rather than specific dates. They used to read the repository the tests themselves live
/// in, which made them depend on how that repository had been assembled — see
/// <see cref="FixtureVaultRepo"/> for what that cost.
/// </summary>
public class GitHistoryReaderTests
{
    private static readonly Regex IsoDate = new(@"^\d{4}-\d{2}-\d{2}$");

    private readonly GitHistoryReader _reader = new();
    private static string VaultRoot => FixtureVaultRepo.Path;

    [Theory]
    [InlineData("docker-basics.md")]
    [InlineData("linux-fundamentals.md")]
    public void TrackedFile_HasIsoDatesOldestFirst(string fileName)
    {
        var filePath = FixtureVaultRepo.FilePath(fileName);

        var history = _reader.GetHistory(VaultRoot, filePath);

        history.Should().NotBeEmpty(because: "the fixture vault is committed to its own repo");
        history.Should().OnlyContain(d => IsoDate.IsMatch(d));
        history.Should().BeInAscendingOrder(because: "git log is read oldest-first");
    }

    [Fact]
    public void NonExistentFile_ReturnsEmptyList_DoesNotThrow()
    {
        var filePath = FixtureVaultRepo.FilePath("does-not-exist.md");

        var history = _reader.GetHistory(VaultRoot, filePath);

        history.Should().BeEmpty();
    }

    [Fact]
    public void FileVendoredBySquashedSubtree_StillHasHistory()
    {
        // Regression: `git log --follow` returns NOTHING for a file that arrived through
        // `git subtree add --squash`. The squashed commit carries the content at the
        // subtree's own root while the mainline holds it under a prefix, and follow's
        // rename detection gives up across that boundary — silently, with exit code 0.
        //
        // This is not a corner case: it is what happens to any vault vendored into a
        // larger repository, and it cost this suite four red tests. A plain `git log`
        // finds the commit, which is why the reader falls back to one.
        var work = Path.Combine(Path.GetTempPath(), $"synapse-subtree-{Guid.NewGuid():N}");
        var upstream = Path.Combine(work, "upstream");
        var host = Path.Combine(work, "host");

        Directory.CreateDirectory(upstream);
        File.WriteAllText(Path.Combine(upstream, "note.md"), "# Note\n");
        GitCommand.Run(upstream, "init", "-q", "-b", "main");
        GitCommand.Run(upstream, "add", "-A");
        GitCommand.Run(upstream, "commit", "-q", "-m", "note");

        GitCommand.InitWithRoot(host);
        GitCommand.Run(host, "subtree", "add", "--prefix=vault", upstream, "main", "--squash");

        var vaultRoot = Path.Combine(host, "vault");
        var history = _reader.GetHistory(vaultRoot, Path.Combine(vaultRoot, "note.md"));

        history.Should().NotBeEmpty(
            because: "the file is in the repository, whatever --follow makes of the merge");
        history.Should().OnlyContain(d => IsoDate.IsMatch(d));
    }
}
