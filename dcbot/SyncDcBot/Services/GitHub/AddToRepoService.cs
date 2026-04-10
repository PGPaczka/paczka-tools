using Microsoft.Extensions.Configuration;
using Octokit;
using Serilog.Events;
using SyncDcBot.Repositories;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

namespace SyncDcBot.Services.GitHub;

public class AddToRepoService
{
    private readonly GitHubClient _github;
    private readonly IConfiguration _config;

    public AddToRepoService(GitHubClient github, IConfiguration config)
    {
        _github = github;
        _config = config;
    }

    public async Task<ServiceResult<GitHubResultType>> AddCollaboratorAsync(string ghUser)
    {
        var owner = _config["GitHubConfig:RepoOwner"];
        var repo  = _config["GitHubConfig:RepoName"];

        var userCheck = await VerifyUserExistsAsync(ghUser);
        if (!userCheck.IsSuccess)
        {
            return userCheck;
        }

        var result = await InviteToRepoAsync(ghUser, owner, repo); 
        return result;
    }

    private async Task<ServiceResult<GitHubResultType>> VerifyUserExistsAsync(string ghUser)
    {
        try
        {
            await _github.User.Get(ghUser);
            return ServiceResult.Create(GitHubResultType.Success);
        }
        catch (NotFoundException)
        {
            return ServiceResult.Create(GitHubResultType.UserNotFound);
        }
    }

    private async Task<ServiceResult<GitHubResultType>> InviteToRepoAsync(string ghUser, string owner, string repo)
    {
        try
        {
            await _github.Repository.Collaborator.Add(owner, repo, ghUser);
            return ServiceResult.Create(GitHubResultType.Success);
        }
        catch (Exception exception)
        {
            return exception switch
            {
                ForbiddenException  => ServiceResult.Create(GitHubResultType.Unauthorized),
                NotFoundException   => ServiceResult.Create(GitHubResultType.RepoNotFound),
                _                   => ServiceResult.Create(GitHubResultType.UnexpectedError, exception.Message)
            };
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