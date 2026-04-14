using System.Net;
using Microsoft.Extensions.Configuration;
using Octokit;
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

    public async Task<ServiceResult<GitHubResultType>> AddCollaboratorAsync(string? ghUsername)
    {
        var owner = _config["GitHubConfig:RepoOwner"]!;
        var repo  = _config["GitHubConfig:RepoName"]!;

        var userCheck = await VerifyUserExistsAsync(ghUsername);
        if (!userCheck.IsSuccess)
        {
            return userCheck;
        }

        var result = await InviteToRepoAsync(ghUsername!, owner, repo); 
        return result;
    }

    private async Task<ServiceResult<GitHubResultType>> VerifyUserExistsAsync(string? ghUsername)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(ghUsername))
            {
                throw new NotFoundException("GitHub username is missing", HttpStatusCode.NotFound);
            }
            await _github.User.Get(ghUsername);
            return ServiceResult.Create(GitHubResultType.Success);
        }
        catch (NotFoundException)
        {
            return ServiceResult.Create(GitHubResultType.UserNotFound);
        }
    }

    private async Task<ServiceResult<GitHubResultType>> InviteToRepoAsync(string ghUsername, string owner, string repo)
    {
        try
        {
            await _github.Repository.Collaborator.Add(owner, repo, ghUsername);
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
    
    public static bool TryParseGitHubLogin(string profileLink, out string ghUsername)
    {
        ghUsername = string.Empty;
        try
        {
            var uri = new Uri(profileLink.TrimEnd('/'));
            var path = uri.AbsolutePath.Trim('/');
            if (string.IsNullOrEmpty(path) || path.Contains('/'))
            {
                return false;
            }
            ghUsername = path;
            return true;
        }
        catch
        {
            return false;
        }
    }
}