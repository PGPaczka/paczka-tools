using FluentAssertions;
using Synapse.Generator.Parsing;
using Synapse.Generator.Tests.Helpers;

namespace Synapse.Generator.Tests.Parsing;

public class YamlFrontmatterReaderTests
{
    private readonly YamlFrontmatterReader _reader = new();

    private static string ReadFixture(string fileName) =>
        File.ReadAllText(FixtureVaultPath.GetFilePath(fileName));

    // docker-basics.md has all five keys: title, category, level, status, tags
    [Fact]
    public void DockerBasics_HasAllExpectedKeys()
    {
        var dict = _reader.Read(ReadFixture("docker-basics.md"));

        dict.Should().ContainKey("title");
        dict.Should().ContainKey("category");
        dict.Should().ContainKey("level");
        dict.Should().ContainKey("status");
        dict.Should().ContainKey("tags");
    }

    // docker-compose.md has no 'category' key (missing from front-matter)
    [Fact]
    public void DockerCompose_DoesNotHaveCategoryKey()
    {
        var dict = _reader.Read(ReadFixture("docker-compose.md"));

        dict.Should().NotContainKey("category");
        dict.Should().ContainKey("title");
        dict.Should().ContainKey("level");
        dict.Should().ContainKey("status");
    }

    // docker-networking.md has no 'level' key (missing from front-matter)
    [Fact]
    public void DockerNetworking_DoesNotHaveLevelKey()
    {
        var dict = _reader.Read(ReadFixture("docker-networking.md"));

        dict.Should().NotContainKey("level");
        dict.Should().ContainKey("title");
        dict.Should().ContainKey("category");
        dict.Should().ContainKey("status");
    }

    // Markdown without a front-matter block returns an empty dictionary
    [Fact]
    public void NoFrontmatter_ReturnsEmptyDictionary()
    {
        var dict = _reader.Read("Just some plain markdown without front-matter.");

        dict.Should().BeEmpty();
    }

    // Unclosed front-matter (no closing ---) returns an empty dictionary
    [Fact]
    public void UnclosedFrontmatter_ReturnsEmptyDictionary()
    {
        var dict = _reader.Read("---\ntitle: Broken\n");

        dict.Should().BeEmpty();
    }
}
