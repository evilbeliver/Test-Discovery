# .NET Rules

## Framework evidence

Recognize NUnit (`NUnit` package, `NUnit.Framework`, `[Test]`, `[TestCase]`, `[TestCaseSource]`), xUnit (`xunit`, `[Fact]`, `[Theory]`, `[InlineData]`, `[MemberData]`, `[ClassData]`), and MSTest (`MSTest.TestFramework`, `[TestMethod]`, `[DataTestMethod]`, `[DataRow]`). Selenium and Microsoft.Playwright package/API evidence may indicate UI automation, but are not test frameworks by themselves. bUnit is a component testing library.

Moq, NSubstitute, and FluentAssertions are supporting libraries, not independent frameworks.

Package references and project markers are declarations; attributes in source are active usage. Count each distinct test method once, collapsing repeated test/data attributes on that method. Data attributes add parameterized inputs, not extra test definitions. `[Fact(Skip = ...)]`, `[Theory(Skip = ...)]`, and method-local `[Ignore]` forms are explicit skip evidence. Ignore attributes must not leak to adjacent methods.

Expose the source method name and first recognized test-attribute line. Resolve the shared `[Theory]` name using an explicit NUnit/xUnit namespace or an unambiguous nearest-project package reference. If neither resolves it, report a limitation rather than arbitrarily assigning a framework.

## Project files

Associate C# source with its nearest `.csproj` and discover `.sln` files as solution evidence. A project is considered a test project when test framework/package evidence or recognized test declarations support that conclusion; names ending in `Tests` alone are not sufficient.

## Limitations

Conditional compilation is handled conservatively for straightforward `#if false` blocks. Complex symbols, aliases, source generators, and conditional package references can affect evidence and are not evaluated.
