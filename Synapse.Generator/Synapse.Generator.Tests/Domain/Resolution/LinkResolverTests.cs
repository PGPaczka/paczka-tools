using FluentAssertions;
using Synapse.Generator.Domain.Links;
using Synapse.Generator.Domain.Mapping;
using Synapse.Generator.Domain.Notes;
using Synapse.Generator.Domain.Resolution;

namespace Synapse.Generator.Tests.Domain.Resolution;

public class LinkResolverTests
{
    private static LinkResolver CreateResolver() => new();

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static RawNote MakeNote(string id, params WikiLinkRef[] links) =>
        new(id, $"{id}.md", new Dictionary<string, object?>(), links, "body");

    private static MappedFrontmatter MakeFm(params string[] aliases) =>
        new("Title", "Cat", null, null, [], aliases, null);

    private static Dictionary<string, MappedFrontmatter> NoFm(IEnumerable<RawNote> notes) =>
        notes.ToDictionary(n => n.Id, _ => MakeFm());

    private static Dictionary<string, MappedFrontmatter> FmWith(
        IEnumerable<RawNote> notes, string noteId, string[] aliases)
    {
        var d = NoFm(notes);
        d[noteId] = MakeFm(aliases);
        return d;
    }

    // ── Tier-2: stem match ────────────────────────────────────────────────────

    [Fact]
    public void StemTier_SimpleLink_ResolvesToTargetId()
    {
        var target = MakeNote("docker-basics");
        var source = MakeNote("dockerfile",
            new WikiLinkRef("[[docker-basics]]", "docker-basics", null, null));
        var notes = new[] { target, source };

        var (links, warnings) = CreateResolver().Resolve(notes, NoFm(notes));

        var link = links.Should().ContainSingle().Subject;
        link.SourceId.Should().Be("dockerfile");
        link.TargetId.Should().Be("docker-basics");
        link.IsGhost.Should().BeFalse();
        warnings.Should().BeEmpty();
    }

    // ── Tier-3: alias match ───────────────────────────────────────────────────

    [Fact]
    public void AliasTier_LinkToAlias_ResolvesToOriginalNote()
    {
        var linuxNote = MakeNote("linux-fundamentals");
        var source = MakeNote("process-scheduling",
            new WikiLinkRef("[[Linux Basics]]", "Linux Basics", null, null));
        var notes = new[] { linuxNote, source };
        var fm = FmWith(notes, "linux-fundamentals", ["Linux Basics"]);

        var (links, _) = CreateResolver().Resolve(notes, fm);

        var link = links.Should().ContainSingle().Subject;
        link.TargetId.Should().Be("linux-fundamentals");
        link.IsGhost.Should().BeFalse();
    }

    // ── Heading-suffix stripping ──────────────────────────────────────────────

    [Fact]
    public void HeadingSuffix_Stripped_ResolvesCorrectly()
    {
        // WikiLinkExtractor already stores only the Target (without #heading) in Target field.
        var compose = MakeNote("docker-compose");
        var source = MakeNote("kubernetes-intro",
            // As the extractor produces: Target="docker-compose", Heading="Scaling"
            new WikiLinkRef("[[docker-compose#Scaling]]", "docker-compose", "Scaling", null));
        var notes = new[] { compose, source };

        var (links, _) = CreateResolver().Resolve(notes, NoFm(notes));

        var link = links.Should().ContainSingle().Subject;
        link.TargetId.Should().Be("docker-compose");
        link.IsGhost.Should().BeFalse();
    }

    // ── Pipe-alias stripping (target not resolvable) ──────────────────────────

    [Fact]
    public void PipeAlias_TargetNotFound_BecomesGhost()
    {
        // [[Kubernetes Advanced|kubernetes-advanced]]: Target="Kubernetes Advanced" — not found
        var source = MakeNote("kubernetes-intro",
            new WikiLinkRef("[[Kubernetes Advanced|kubernetes-advanced]]",
                "Kubernetes Advanced", null, "kubernetes-advanced"));
        var notes = new[] { source };

        var (links, _) = CreateResolver().Resolve(notes, NoFm(notes));

        var link = links.Should().ContainSingle().Subject;
        link.IsGhost.Should().BeTrue();
        link.TargetId.Should().BeNull();
    }

    // ── Unresolved → ghost ────────────────────────────────────────────────────

    [Fact]
    public void Unresolved_Link_IsGhost()
    {
        var source = MakeNote("source",
            new WikiLinkRef("[[does-not-exist]]", "does-not-exist", null, null));
        var notes = new[] { source };

        var (links, _) = CreateResolver().Resolve(notes, NoFm(notes));

        links.Should().ContainSingle()
            .Which.IsGhost.Should().BeTrue();
    }

    // ── Duplicate stem → warning ──────────────────────────────────────────────

    [Fact]
    public void DuplicateStem_TwoNotes_EmitsWarning()
    {
        // Two notes with id = "docker-basics" (same stem) from different files isn't
        // normally possible via the scanner, but the resolver must handle it gracefully
        // and emit a duplicate-id warning.
        var note1 = new RawNote("docker-basics", "devops/docker-basics.md",
            new Dictionary<string, object?>(), [], "body");
        var note2 = new RawNote("docker-basics", "tools/docker-basics.md",
            new Dictionary<string, object?>(), [], "body");
        var notes = new[] { note1, note2 };
        // Build frontmatter dict manually to avoid duplicate-key crash in ToDictionary
        var fm = new Dictionary<string, MappedFrontmatter> { ["docker-basics"] = MakeFm() };

        var (_, warnings) = CreateResolver().Resolve(notes, fm);

        warnings.Should().ContainSingle()
            .Which.Kind.Should().Be("duplicate-id");
    }

    // ── LinkText preserves full raw wikilink ──────────────────────────────────

    [Fact]
    public void LinkText_IsFullRawWikilink()
    {
        var target = MakeNote("docker-basics");
        var source = MakeNote("dockerfile",
            new WikiLinkRef("[[docker-basics]]", "docker-basics", null, null));
        var notes = new[] { target, source };

        var (links, _) = CreateResolver().Resolve(notes, NoFm(notes));

        links[0].LinkText.Should().Be("[[docker-basics]]");
    }

    // ── Multiple links from one note ──────────────────────────────────────────

    [Fact]
    public void MultipleLinksInOneNote_AllResolved()
    {
        var target1 = MakeNote("docker-compose");
        var linuxNote = MakeNote("linux-fundamentals");
        var source = MakeNote("kubernetes-intro",
            new WikiLinkRef("[[docker-compose#Scaling]]", "docker-compose", "Scaling", null),
            new WikiLinkRef("[[Kubernetes Advanced|kubernetes-advanced]]",
                "Kubernetes Advanced", null, "kubernetes-advanced"));
        var notes = new[] { target1, linuxNote, source };

        var (links, _) = CreateResolver().Resolve(notes, NoFm(notes));

        links.Should().HaveCount(2);
        links.Should().ContainSingle(l => l.TargetId == "docker-compose" && !l.IsGhost);
        links.Should().ContainSingle(l => l.IsGhost);
    }
}
