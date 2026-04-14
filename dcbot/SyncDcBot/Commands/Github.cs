using Discord.Interactions;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Repositories;
using SyncDcBot.Services.GitHub;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

namespace SyncDcBot.Commands;

public class GitHubModule(AddToRepoService github, BypassPrRulesService bypassPrRulesService, CommandResultStore resultStore, IConfiguration config)
    : CommandBase(resultStore)
{
    private static readonly string _adminRoleId = null!;
    [SlashCommand("dodaj-do-repo", "Adds user to Paczka github repo")]
    [RequireConfiguredRole("DiscordConfig:AdminRoleId")]
    public async Task AddToRepoAsync(
        [Summary("profile", "Link to GitHub profile (eg. https://github.com/jankowalski)")]
        string profile)
    {
        var owner = config["GitHubConfig:RepoOwner"];
        var repo  = config["GitHubConfig:RepoName"];
        
        if (!AddToRepoService.TryParseGitHubLogin(profile, out var ghUser))
        {
            ResultStore.SetFailure(Context.Interaction.Id, "Incorrect GitHub profile link.");
            return;
        }

        await DeferAsync();

        var result = await github.AddCollaboratorAsync(ghUser);
        var x = result.Type switch
        {
            GitHubResultType.Success            => CommandResult.Success($"User **{ghUser}** was invited to `{owner}/{repo}`! Invitation must be accepted on GitHub."),
            GitHubResultType.UserNotFound       => CommandResult.Failure($"User {ghUser} not found on GitHub."),
            GitHubResultType.RepoNotFound       => CommandResult.GeneralError(logMsg: $"{owner}/{repo} repo not found. Check configuration."),
            GitHubResultType.Unauthorized       => CommandResult.GeneralError(logMsg: "Bot is not authorized to access the repo."),
            GitHubResultType.UnexpectedError    => CommandResult.GeneralError(logMsg: $"UnexpectedError: {result.Message!}"),
            _                                   => throw new ArgumentOutOfRangeException(nameof(result.Type), result.Type, null)
        };
        ResultStore.Set(Context.Interaction.Id, x);
    }
    

    [SlashCommand("bypass-merge", "Bypass PR rules and merge pull request")]
    [RequireConfiguredRole("DiscordConfig:AdminRoleId")]
    public async Task BypassMergeAsync(
        [Summary("pr-url", "Full URL of the pull request")] 
        string prUrl)
    {
        await Context.Interaction.DeferAsync();

        var result = await bypassPrRulesService.BypassMergePullRequestAsync(prUrl);

        var commandResult = result.Type switch
        {
            BypassMergeResultType.Success               => CommandResult.Success($"PR merged successfully: {prUrl}"),
            BypassMergeResultType.InvalidUrl            => CommandResult.Failure(result.Message),
            BypassMergeResultType.InvalidPrNumberFormat => CommandResult.Failure("Could not parse PR number from the URL."),
            BypassMergeResultType.NotFound              => CommandResult.Failure($"PR or its branch no longer exists."),
            BypassMergeResultType.AlreadyClosed         => CommandResult.Failure("This pull request is already closed."),
            BypassMergeResultType.AlreadyMerged         => CommandResult.Failure("This pull request is already merged."),
            BypassMergeResultType.ForcePushDetected     => CommandResult.Failure(result.Message),
            BypassMergeResultType.NotMergeable          => CommandResult.Failure("Pull request is not mergeable. Check for conflicts."),
            BypassMergeResultType.UnexpectedError       => CommandResult.GeneralError(result.Message!),
            _                                           => throw new ArgumentOutOfRangeException(nameof(result.Type), result.Type, null)
        };
        
        ResultStore.Set(Context.Interaction.Id, commandResult);
    }
    
    
}