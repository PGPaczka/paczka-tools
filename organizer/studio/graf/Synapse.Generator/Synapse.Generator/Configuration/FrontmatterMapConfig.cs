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
    string RelationsKey = "relations",
    // Identity and metrics of the CONTENT a note stands for, when it stands for one.
    // A vault of plain notes leaves these absent; a vault generated from an index uses
    // them so a viewer can address the content itself instead of parsing the excerpt.
    string Sha256Key = "sha256",
    string SizeBytesKey = "sizeBytes",
    string ContentKindKey = "contentKind",
    // A structured block the vault owns end to end: the generator carries it to
    // graph.json without knowing its shape, so the vault can change it alone.
    string FileKey = "file"
);
