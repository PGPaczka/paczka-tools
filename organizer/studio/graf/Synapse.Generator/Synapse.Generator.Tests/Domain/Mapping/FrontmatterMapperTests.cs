using FluentAssertions;
using Synapse.Generator.Configuration;
using Synapse.Generator.Domain.Mapping;

namespace Synapse.Generator.Tests.Domain.Mapping;

public class FrontmatterMapperTests
{
    private static ConfigurableFrontmatterMapper CreateMapper() =>
        new(new FrontmatterMapConfig());

    // ── Full frontmatter ──────────────────────────────────────────────────────

    [Fact]
    public void FullFrontmatter_MapsAllFields()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?>
        {
            ["title"]    = "Docker Basics",
            ["category"] = "DevOps",
            ["level"]    = "1",
            ["status"]   = "completed",
            ["tags"]     = new List<object> { "containers", "cli" },
            ["aliases"]  = new List<object> { "Docker 101" },
            ["modified"] = "2026-03-10"
        };

        var result = mapper.Map(fm, "docker-basics.md");

        result.Title.Should().Be("Docker Basics");
        result.Category.Should().Be("DevOps");
        result.Level.Should().Be(1);
        result.Status.Should().Be("completed");
        result.Tags.Should().Equal("containers", "cli");
        result.Aliases.Should().Equal("Docker 101");
        result.Modified.Should().Be("2026-03-10");
    }

    // ── Missing / default fields ──────────────────────────────────────────────

    [Fact]
    public void MissingCategory_DefaultsToUncategorized()
    {
        var mapper = CreateMapper();
        var result = mapper.Map(new Dictionary<string, object?>(), "note.md");
        result.Category.Should().Be("Uncategorized");
    }

    [Fact]
    public void MissingLevel_ReturnsNull()
    {
        var mapper = CreateMapper();
        var result = mapper.Map(new Dictionary<string, object?>(), "note.md");
        result.Level.Should().BeNull();
    }

    [Fact]
    public void MissingTitle_UsesFilenameStem()
    {
        var mapper = CreateMapper();
        var result = mapper.Map(new Dictionary<string, object?>(), "my-note.md");
        result.Title.Should().Be("my-note");
    }

    [Fact]
    public void MissingTagsAndAliases_ReturnEmptyLists()
    {
        var mapper = CreateMapper();
        var result = mapper.Map(new Dictionary<string, object?>(), "note.md");
        result.Tags.Should().BeEmpty();
        result.Aliases.Should().BeEmpty();
    }

    // ── Tags coercion ─────────────────────────────────────────────────────────

    [Fact]
    public void TagsAsCommaString_SplitsAndTrims()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["tags"] = "foo, bar" };
        var result = mapper.Map(fm, "note.md");
        result.Tags.Should().Equal("foo", "bar");
    }

    [Fact]
    public void TagsAsYamlList_CorrectStringList()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["tags"] = new List<object> { "containers", "cli" } };
        var result = mapper.Map(fm, "note.md");
        result.Tags.Should().Equal("containers", "cli");
    }

    [Fact]
    public void TagsAsSingleScalar_TreatedAsSingleElement()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["tags"] = (object)"single-tag" };
        var result = mapper.Map(fm, "note.md");
        result.Tags.Should().Equal("single-tag");
    }

    // ── Status normalisation ──────────────────────────────────────────────────

    [Fact]
    public void Status_InProgress_NormalisedLower()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["status"] = "in-progress" };
        mapper.Map(fm, "note.md").Status.Should().Be("in-progress");
    }

    [Fact]
    public void Status_COMPLETED_UpperCase_NormalisedToLower()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["status"] = "COMPLETED" };
        mapper.Map(fm, "note.md").Status.Should().Be("completed");
    }

    [Fact]
    public void Status_Unknown_ReturnsNull()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["status"] = "unknown" };
        mapper.Map(fm, "note.md").Status.Should().BeNull();
    }

    [Fact]
    public void Status_NotStarted_Normalised()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["status"] = "not-started" };
        mapper.Map(fm, "note.md").Status.Should().Be("not-started");
    }
}
