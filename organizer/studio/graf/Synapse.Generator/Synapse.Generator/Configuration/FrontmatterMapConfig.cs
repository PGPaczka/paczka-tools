namespace Synapse.Generator.Configuration;

public record FrontmatterMapConfig(
    string CategoryKey = "category",
    string LevelKey = "level",
    string StatusKey = "status",
    string TagsKey = "tags",
    string AliasesKey = "aliases",
    string TitleKey = "title",
    string ModifiedKey = "modified",
    // What a note IS in the vault's own taxonomy (e.g. semester / subject / file).
    string TypeKey = "type",
    // Typed relations: a sequence of { target, kind, confidence } mappings.
    string RelationsKey = "relations"
);
