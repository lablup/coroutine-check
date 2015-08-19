# coroutine-check
Analyzes a Python source file and warn if a coroutine is not called in a proper way (yield from or await).
The input file is parsed into an AST (abstract syntax tree), and we apply 3-step scanner:

## How it works

 1. ImportRetriever: scan import statements and perform the imports into a separate namespace.
 2. CoroutineDefFinder: (a preprocessor)
  - scans all function definitions and store their "scoped path" to mark that they are coroutines
  - scans all assignments and store their "scoped type" information
    (to let this work, method/function arguments should be annotated with explicit types.)
 3. CoroutineChecker: (the main processor)
  - scans all function calls and matches its call syntax (yield from) with whether it is a coroutine or not.
    It uses the attribute information preprocessed by CoroutineDefFinder and on-the-fly evaluation of the attributes using the external dependencies loaded in the step 1.
  - prints the function calls and wheter they are coroutines or not. The color means that the calling syntax is correct (green) or not (red) for each call.

## Limitation

Since Python is a dynamically typed language, it is impossible to determine the object type in the compile time or via an static analysis.
This is why this script requires explicit argument annotations for the step 2.

## Meaning of this work

I tried to cover most&mdash;to say, 90%&mdash;of use cases to practically prevent silly mistakes such as missing "yield from".  This nowhere targets to cover all the corner cases and dynamic cases.  
Unfortunately, some asyncio-based libraries such as asyncio_redis dynamically generates its API methods in run time, so we cannot determine if the method calls are coroutines or not using this tool. :(

Nonetheless, this code also serves as a demonstrative example of the AST package to traverse and transform Python codes.
