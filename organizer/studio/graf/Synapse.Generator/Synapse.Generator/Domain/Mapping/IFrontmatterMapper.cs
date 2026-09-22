namespace Synapse.Generator.Domain.Mapping;

public interface IFrontmatterMapper
{
    MappedFrontmatter Map(Dictionary<string, object?> frontmatter, string fileName);
}
