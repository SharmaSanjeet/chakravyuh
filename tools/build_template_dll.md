# Generating the forge template (decompilable .NET DLL)

The forge (`chakravyuh/decoys.py`) serves decoy binaries with embedded credentials.
For the decoy to be a **real, decompilable .NET DLL** (dnSpy/ILSpy) without requiring
the .NET SDK at runtime, we start from a **pre-forged template** that is generated
**once, offline**, and whose bytes are then patched per deployment.

If the template is not present, the forge degrades to a PE binary with the
credentials embedded in plain text (recoverable with `strings`). Everything keeps
working; only the "pretty" decompilation is lost.

## Requirement

The template MUST contain these fixed-width literals (patching respects their exact
length so the PE metadata is not shifted):

| Field              | Placeholder (ASCII)                 | Length |
|--------------------|-------------------------------------|----------|
| connection_string  | `CKCONN__` + `0` × 120              | 128      |
| internal_api_base  | `CKAPI__` + `0` × 57                | 64       |
| bearer_token       | `CKBEARER__` + `0` × 118            | 128      |

## Steps (with the .NET SDK on a build machine)

1. Create a library project:

   ```bash
   dotnet new classlib -n PortalTemplate -o portal-template
   ```

2. Replace `Class1.cs` with a class that has the placeholders as constants:

   ```csharp
   namespace Portal.Internal
   {
       internal static class AppConfig
       {
           public const string ConnectionString =
               "CKCONN__000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000";
           public const string InternalApiBase =
               "CKAPI__000000000000000000000000000000000000000000000000000";
           // Service token (would be encrypted in a real deployment; a constant here for the decoy).
           public const string ServiceToken =
               "CKBEARER__000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000";
       }
   }
   ```

3. Build in Release and copy the DLL into the package assets:

   ```bash
   dotnet build -c Release portal-template
   cp portal-template/bin/Release/*/PortalTemplate.dll chakravyuh/assets/portal_template.dll
   ```

The forge detects `chakravyuh/assets/portal_template.dll` automatically. To use
another path, pass it when constructing `AssemblyForge(template_path=...)`.

> Note: the placeholders are UTF-16 literals in the PE `#US` heap; patching
> looks for their UTF-16LE encoding and replaces it with the deployment value
> (padded with deterministic base62 up to the same length).
