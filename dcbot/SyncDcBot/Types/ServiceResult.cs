namespace SyncDcBot.Types;

public record ServiceResult<TType>(TType Type, string? Message = null) where TType : Enum
{
    public bool IsSuccess => Equals(Type, GetSuccessValue());
    
    private static TType GetSuccessValue() 
        => (TType)Enum.Parse(typeof(TType), "Success");
}
