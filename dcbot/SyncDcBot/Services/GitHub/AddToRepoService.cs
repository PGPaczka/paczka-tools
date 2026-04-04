using Microsoft.Extensions.Configuration;
using Octokit;
using Serilog.Events;
using SyncDcBot.Repositories;

namespace SyncDcBot.Services;

public record GitHubResult(bool Success, string Message, LogEventLevel LogLevel);

public class AddToRepoService
{
    private readonly GitHubClient _github;
    private readonly IConfiguration _config;

    public AddToRepoService(GitHubClient github, IConfiguration config)
    {
        _github = github;
        _config = config;
    }

    public async Task<GitHubResult> AddCollaboratorAsync(string ghUser)
    {
        var owner = _config["RepoOwner"];
        var repo  = _config["RepoName"];

        var userCheck = await VerifyUserExistsAsync(ghUser);
        if (!userCheck.Success)
        {
            return userCheck;
        }

        return await InviteToRepoAsync(ghUser, owner, repo);
    }

    private async Task<GitHubResult> VerifyUserExistsAsync(string ghUser)
    {
        try
        {
            await _github.User.Get(ghUser);
            return new GitHubResult(true, "User found.", LogEventLevel.Debug);
        }
        catch (NotFoundException)
        {
            return new GitHubResult(false, $"{EmojiRepo.ErrorEmoji} User `{ghUser}` not found on GitHub.", LogEventLevel.Warning);
        }
    }

    private async Task<GitHubResult> InviteToRepoAsync(string ghUser, string owner, string repo)
    {
        try
        {
            await _github.Repository.Collaborator.Add(owner, repo, ghUser);
            
            return new GitHubResult(true,
                $"{EmojiRepo.SuccessEmoji} User **{ghUser}** was invited to `{owner}/{repo}`! It must be accepted on GitHub.", 
                LogEventLevel.Information);
        }
        catch (ForbiddenException)
        {
            return new GitHubResult(false, 
                $"{EmojiRepo.ErrorEmoji} Bot has no permissions to manage {owner}/{repo}.", 
                LogEventLevel.Warning);
        }
        catch (NotFoundException)
        {
            return new GitHubResult(false, 
                $"{EmojiRepo.ErrorEmoji} Bot error configuration. Contact bot maintainer.", 
                LogEventLevel.Warning);
        }
        catch (Exception ex)
        {
            return new GitHubResult(false, 
                $"{EmojiRepo.ErrorEmoji} Unexpected error: {ex.Message}", 
                LogEventLevel.Warning);
        }
    }
    
    public static bool TryParseGitHubLogin(string profile, out string login)
    {
        login = string.Empty;
        try
        {
            var uri = new Uri(profile.TrimEnd('/'));
            var path = uri.AbsolutePath.Trim('/');
            if (string.IsNullOrEmpty(path) || path.Contains('/'))
            {
                return false;
            }
            login = path;
            return true;
        }
        catch
        {
            return false;
        }
    }
}