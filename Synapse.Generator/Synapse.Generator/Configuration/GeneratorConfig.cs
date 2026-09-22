namespace Synapse.Generator.Configuration;

public record GeneratorConfig(
    FrontmatterMapConfig FrontmatterMap,
    string VaultPath,
    string OutputPath,
    // Skip `git log` per note. A generated vault is often not a repository at all, and
    // shelling out once per file only to fail is pure cost: with a few thousand notes that
    // is a few thousand processes. `history` is then simply absent, which the schema allows.
    bool SkipGitHistory = false
);
