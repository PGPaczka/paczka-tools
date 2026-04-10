namespace SyncDcBot.Types.Enums;

public enum GitHubResultType
{
    Success, 
    UserNotFound, 
    RepoNotFound, 
    Unauthorized,
    UnexpectedError
}