using System.Text.Json.Nodes;
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

    // ── Content identity (sha256 / sizeBytes / contentKind) ───────────────────

    [Fact]
    public void ContentIdentity_IsMappedWhenDeclared()
    {
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?>
        {
            ["sha256"]      = new string('a', 64),
            ["sizeBytes"]   = "172032",
            ["contentKind"] = "image"
        };

        var result = mapper.Map(fm, "note.md");

        result.Sha256.Should().Be(new string('a', 64));
        result.SizeBytes.Should().Be(172032);
        result.ContentKind.Should().Be("image");
    }

    [Fact]
    public void ContentIdentity_IsNullWhenAbsent()
    {
        var mapper = CreateMapper();

        var result = mapper.Map(new Dictionary<string, object?>(), "note.md");

        result.Sha256.Should().BeNull();
        result.SizeBytes.Should().BeNull();
        result.ContentKind.Should().BeNull();
    }

    [Fact]
    public void SizeBytes_BeyondIntRange_IsKept()
    {
        // A recording in 90_MEDIA can pass 2 GB; int would silently wrap it to nonsense.
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?> { ["sizeBytes"] = "3221225472" };

        mapper.Map(fm, "note.md").SizeBytes.Should().Be(3221225472L);
    }

    // ── Nested `file` block (schema v4) ──────────────────────────────────────

    [Fact]
    public void FileBlock_KeepsItsShapeAndTypes()
    {
        // The vault writes a nested block so a viewer can lay a file note out from data
        // instead of parsing prose. Types matter: a confidence that arrives as the string
        // "0.9" is not a number any reader can compare, and a path that arrives as a
        // number stops being a path.
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?>
        {
            ["file"] = new Dictionary<object, object>
            {
                ["decision"] = new Dictionary<object, object>
                {
                    ["action"] = "copy",
                    ["confidence"] = 0.9,
                    ["inPackage"] = false,
                },
                ["provenance"] = new Dictionary<object, object>
                {
                    ["total"] = 260,
                    ["copies"] = new List<object>
                    {
                        new Dictionary<object, object> { ["package"] = "Paczki Infa", ["path"] = "3 SEM/x.pdf" },
                    },
                },
            },
        };

        var file = mapper.Map(fm, "note.md").File;

        file.Should().NotBeNull();
        file!["decision"]!["action"]!.GetValue<string>().Should().Be("copy");
        file["decision"]!["confidence"]!.GetValue<double>().Should().Be(0.9);
        file["decision"]!["inPackage"]!.GetValue<bool>().Should().BeFalse();
        // Whole numbers are widened on purpose: a file size does not fit an int.
        file["provenance"]!["total"]!.GetValue<long>().Should().Be(260);
        file["provenance"]!["copies"]![0]!["package"]!.GetValue<string>().Should().Be("Paczki Infa");
    }

    [Fact]
    public void FileBlock_IsNullWhenAbsent()
    {
        CreateMapper().Map(new Dictionary<string, object?>(), "note.md").File.Should().BeNull();
    }

    [Fact]
    public void FileBlock_SurvivesAValueThatLooksLikeSomethingElse()
    {
        // A source folder really can be called "true" or "260". The vault quotes every
        // string it writes, so such a value arrives here already as a string — and must
        // stay one.
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?>
        {
            ["file"] = new Dictionary<object, object> { ["provenance"] = new Dictionary<object, object>
            {
                ["copies"] = new List<object>
                {
                    new Dictionary<object, object> { ["package"] = "true", ["path"] = "260" },
                },
            } },
        };

        var copy = mapper.Map(fm, "note.md").File!["provenance"]!["copies"]![0]!;

        copy["package"]!.GetValue<string>().Should().Be("true");
        copy["path"]!.GetValue<string>().Should().Be("260");
    }

    [Fact]
    public void FileBlock_DoesNotWidenAFloatIntoNoise()
    {
        // The YAML reader parses an unquoted `0.9` as a float. Widening that to a double
        // keeps the single-precision error, and the graph then carries 0.8999999761581421
        // where the vault wrote 0.9. Caught by the contract test against the real generator.
        var mapper = CreateMapper();
        var fm = new Dictionary<string, object?>
        {
            ["file"] = new Dictionary<object, object> { ["decision"] = new Dictionary<object, object>
            {
                ["confidence"] = 0.9f,
            } },
        };

        var value = mapper.Map(fm, "note.md").File!["decision"]!["confidence"]!;

        value.GetValue<double>().Should().Be(0.9);
    }
}
