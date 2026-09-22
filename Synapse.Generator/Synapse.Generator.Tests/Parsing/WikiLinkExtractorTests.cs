using FluentAssertions;
using Synapse.Generator.Parsing;
using Synapse.Generator.Tests.Helpers;

namespace Synapse.Generator.Tests.Parsing;

public class WikiLinkExtractorTests
{
    private readonly WikiLinkExtractor _extractor = new(new MarkdigNoteParser());

    private static string ReadFixture(string fileName) =>
        File.ReadAllText(FixtureVaultPath.GetFilePath(fileName));

    // dockerfile.md has [[docker-basics]] in a paragraph AND [[not-a-link]] inside a
    // fenced code block — only the paragraph link should be extracted.
    [Fact]
    public void Dockerfile_ExtractsOnlyOneLinkOutsideCodeBlock()
    {
        var links = _extractor.Extract(ReadFixture("dockerfile.md"));

        links.Should().HaveCount(1);
        links[0].Target.Should().Be("docker-basics");
        links[0].Heading.Should().BeNull();
        links[0].Alias.Should().BeNull();
    }

    // kubernetes-intro.md has two links:
    //   [[Kubernetes Advanced|kubernetes-advanced]]  → Target="Kubernetes Advanced", Alias="kubernetes-advanced"
    //   [[docker-compose#Scaling]]                   → Target="docker-compose", Heading="Scaling"
    [Fact]
    public void KubernetesIntro_ExtractsTwoLinksWithCorrectParts()
    {
        var links = _extractor.Extract(ReadFixture("kubernetes-intro.md"));

        links.Should().HaveCount(2);

        var aliasLink = links.Should().ContainSingle(l => l.Alias == "kubernetes-advanced").Subject;
        aliasLink.Target.Should().Be("Kubernetes Advanced");
        aliasLink.Heading.Should().BeNull();

        var headingLink = links.Should().ContainSingle(l => l.Target == "docker-compose").Subject;
        headingLink.Heading.Should().Be("Scaling");
        headingLink.Alias.Should().BeNull();
    }

    // vim-shortcuts.md has no wikilinks at all.
    [Fact]
    public void VimShortcuts_ExtractsZeroLinks()
    {
        var links = _extractor.Extract(ReadFixture("vim-shortcuts.md"));

        links.Should().BeEmpty();
    }

    // Inline unit test: plain [[Target]] splits correctly.
    [Fact]
    public void PlainLink_ParsesTargetOnly()
    {
        var links = _extractor.Extract("See [[my-note]] for details.");

        links.Should().HaveCount(1);
        links[0].Target.Should().Be("my-note");
        links[0].Heading.Should().BeNull();
        links[0].Alias.Should().BeNull();
    }

    // Inline unit test: [[Target#Heading|Alias]] is fully split.
    [Fact]
    public void FullLink_ParsesTargetHeadingAlias()
    {
        var links = _extractor.Extract("Check [[MyNote#Section One|the section]].");

        links.Should().HaveCount(1);
        links[0].Target.Should().Be("MyNote");
        links[0].Heading.Should().Be("Section One");
        links[0].Alias.Should().Be("the section");
    }
}
