using System.Text.RegularExpressions;
using FluentAssertions;
using Synapse.Generator.Git;
using Synapse.Generator.Tests.Helpers;

namespace Synapse.Generator.Tests.Git;

/// <summary>
/// Integration tests that shell out to the real git repository containing Fixtures/Vault/.
///
/// These deliberately assert the CONTRACT (dates exist, are ISO yyyy-mm-dd, oldest first)
/// rather than specific dates: commit dates depend on who cloned the repository and when,
/// so hard-coded ones only passed on the machine that authored the fixtures.
/// </summary>
public class GitHistoryReaderTests
{
    private static readonly Regex IsoDate = new(@"^\d{4}-\d{2}-\d{2}$");

    private readonly GitHistoryReader _reader = new();
    private static string VaultRoot => FixtureVaultPath.GetPath();

    [Theory]
    [InlineData("docker-basics.md")]
    [InlineData("linux-fundamentals.md")]
    public void TrackedFile_HasIsoDatesOldestFirst(string fileName)
    {
        var filePath = FixtureVaultPath.GetFilePath(fileName);

        var history = _reader.GetHistory(VaultRoot, filePath);

        history.Should().NotBeEmpty(because: "the fixture vault is committed to the repository");
        history.Should().OnlyContain(d => IsoDate.IsMatch(d));
        history.Should().BeInAscendingOrder(because: "git log is read oldest-first");
    }

    [Fact]
    public void NonExistentFile_ReturnsEmptyList_DoesNotThrow()
    {
        var filePath = FixtureVaultPath.GetFilePath("does-not-exist.md");

        var history = _reader.GetHistory(VaultRoot, filePath);

        history.Should().BeEmpty();
    }
}
