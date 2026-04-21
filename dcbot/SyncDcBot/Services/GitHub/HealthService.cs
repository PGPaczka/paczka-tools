using Octokit;

namespace SyncDcBot.Services.GitHub;

public class HealthService
{
    private readonly GitHubClient _github;

    public HealthService(GitHubClient github)
    {
        _github = github;
    }

    public async Task<bool> PingAsync()
    {
        try
        {
            await _github.RateLimit.GetRateLimits();
            return true;
        }
        catch
        {
            return false;
        }
    }
}