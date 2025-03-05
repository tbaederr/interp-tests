import std.stdio;
import std.algorithm;
import std.array;
import std.string;
import std.range;
import std.file;
import std.conv : to;


immutable int TABLE_LIMIT = 5;
immutable string CLANG_TEST_BASE_DIR = "/home/tbaeder/code/llvm-project/clang/test/";
immutable string LIBCXX_TEST_BASE_DIR = "/home/tbaeder/code/llvm-project/libcxx/test/";

struct Test {
  string file;
  bool isLibcxx;
  bool opCmp(ref Test Other) {
    return Other.file < file;
  }
  string toString() { return file; }
}

struct TestFileData  {
  string name;
  bool[string] failedClangTests;
  bool[string] failedLibcxxTests;

  Test[] regressions;
  Test[] fixed;
  int failedTestsDiff; // diff to previous date.
  int numErrors;

  size_t numFailedTests() const {
    return failedClangTests.length + failedLibcxxTests.length;
  }
}

string dateFromFilename(string filename) {
  filename = filename[filename.indexOf('/') + 1..$];
  filename = filename[0..filename.lastIndexOf('.')];
  return filename;
}

string loadFile(ref Test t) {
  try {
    if (t.isLibcxx)
      return readText(LIBCXX_TEST_BASE_DIR ~ t.file);
    else
      return readText(CLANG_TEST_BASE_DIR ~ t.file);
  } catch(Throwable) {
    stderr.writeln("Couldn't load ", CLANG_TEST_BASE_DIR ~ t.file);
    return "";
  }
}

immutable string preamble = "
<!DOCTYPE html>
<html>
<script src=\"https://cdnjs.cloudflare.com/ajax/libs/Chart.js/2.9.4/Chart.js\"></script>
<style>
  * {
    font-family: Arial;
    font-size: 12px;
  }
  h1 { font-size: 1.9em; }
  em {
    font-family: monospace;
  }

  table {
    background-color: #777;
  }
  th, td {
    background-color: #fff;
    padding: 0 1em 0 1em;
    vertical-align: top;
  }

  td {
    padding: 1em;
  }
  .failuretable {
     margin-top: 2em;
  }

  ul {
    padding: 0 1em 0 1em;
    margin: 0;
  }

  .pos {
    color: #73B66B;
  }
  .neg {
    color: #FF6D31;
  }
  .num {
    text-align: center;
  }
  .slim {
    padding: 0 1em 0 1em;
  }
  .hardfail {
    color: #8b0000;
    margin-right: 0.3em;
    font-size: 70%;
  }
  .note {
    color: #00308F;
    margin-right: 0.3em;
    font-size: 70%;
  }
</style>
<body>
  <h1>Test failures</h1>

<table>
  <tr>
    <th colspan='2'>Allowlist</th>
  </tr>
  <tr>
    <th>Test</th>
    <th>Reason</th>
  </tr>

  <!-- ------>
  <tr>
    <td class='slim'><em>SemaCXX/source_location.cpp</em></td>
    <td class='slim'>The new interpreter is correct.</td>
  </tr>
  <tr>
    <td class='slim'><em>SemaCXX/constexpr-vector-access-elements.cpp</em></td>
    <td class='slim'>The new interpreter is correct.</td>
  </tr>
  <tr>
    <td class='slim'><em>Sema/builtin-memcpy.c</em></td>
    <td class='slim'>The new interpreter is correct.</td>
  </tr>
  <tr>
    <td class='slim'><em>CodeGenObjC/encode-test-4.m</em></td>
    <td class='slim'>Comparison against @encode is unspecified.</td>
  </tr>
  <tr>
    <td class='slim'><em>SemaCXX/new-delete.cpp</em></td>
    <td class='slim'>Diagnostic differences are okay.</td>
  </tr>
  <tr>
    <td class='slim'><em>SemaCXX/builtin-std-move.cpp</em></td>
    <td class='slim'>Diagnostic differences are okay.</td>
  </tr>


</table>

<p>
<a href='https://github.com/tbaederr/interp-tests'>Source Code</a>
</p>
<canvas id=\"allChart\" style=\"width:100%; max-width:900px\"></canvas>

<script>

function listElements(arr, elementName) {
  let res = []
  arr.forEach((e) => {
    res.push(e[elementName]);
  });
  return res;
}


const allData = {
  labels: [ALL_LABELS],
  borderColor: '#0f0',

  datasets: [
    {
      label: 'check-clang',
      data: [CLANG_DATA],
      stepped: true,
      borderColor: '#003f5c',

      backgroundColor: '#009ee6',
    },
    {
      label: 'check-cxx',
      data: [LIBCXX_DATA],
      stepped: true,
      borderColor: '#ffa600',
      backgroundColor: '#ffce72',
    },
  ],
};

const allConfig = {
  type: 'line',
  data: allData,
  plugins: {
    responsive: true,
    title: {
      display: false,
    },
  },
  interaction: {
    intersect: false,
  },
  options: {
    stacked: false,
    scales: {
      x: {
        display: true,
        title: {
          display: true
        }
      },
      y: {
        display: true,
        title: {
          display: true,
          text: 'Value'
        },
        suggestedMin: 0,
        suggestedMax: 600
      }
    }
  }
};


new Chart(\"allChart\", allConfig);
</script>
";


void main(string[] args) {
  if (args.length == 1) {
    writeln("Need filename argument");
    return;
  }
  TestFileData[] testFiles;

  string[] filenames = sort(args[1..$]).array;
  foreach (file; filenames) {
    size_t failed = 0;

    TestFileData tf;
    tf.name = file;

    foreach(line; File(file).byLine()) {
      if (line.strip().startsWith("Clang :: ") ||
          line.strip().startsWith("Clang-Unit :: ")) {
        auto colonColonIndex = line.indexOf(" :: ");
        string name = to!string(line[colonColonIndex + 4..$].strip());
        tf.failedClangTests[name] = true;
      } else if (line.strip().startsWith("llvm-libc++-shared.cfg.in ::")) {
        auto colonColonIndex = line.indexOf(" :: ");
        string name = to!string(line[colonColonIndex + 4..$].strip());
        tf.failedLibcxxTests[name] = true;
      }
      if (line.endsWith("errors generated.") &&
          line.split(' ').length == 3) {
        auto n = to!size_t(line[0..line.indexOf(' ')]);
        tf.numErrors += n;
      }
    }
    testFiles ~= tf;
  }

  // Create label string.
  string labels;
  foreach (ref t; testFiles) {
    labels ~= "'" ~ t.name.replace("../", "").replace(".txt", "") ~ "',";
  }

  // Data string.
  string clangData;
  foreach (ref t; testFiles) {
    clangData ~= to!string(t.failedClangTests.length) ~ ", ";
  }

  string libcxxData;
  foreach (ref t; testFiles) {
    libcxxData ~= to!string(t.failedLibcxxTests.length) ~ ", ";
  }

  writeln(preamble.replace("ALL_LABELS", labels).replace("CLANG_DATA", clangData).replace("LIBCXX_DATA", libcxxData));

  writeln(
      "<table class='failuretable'>
        <tr>
          <th>Date</th>
          <th>Failures</th>
          <th>Errors</th>
          <th>Diff</th>
          <th>Regressions</th>
          <th>Fixed</th>
        </tr>
        ");

  // Compute regressions.

  size_t fileIndex = 1;
  foreach (ref testFile; testFiles.drop(1)) {
    const TestFileData* prev = &testFiles[fileIndex - 1];

    foreach (ref test; testFile.failedClangTests.keys) {
      if (test !in prev.failedClangTests)
        testFile.regressions ~= Test(test, false);
    }
    foreach (ref test; testFile.failedLibcxxTests.keys) {
      if (test !in prev.failedLibcxxTests)
        testFile.regressions ~= Test(test, true);
    }

    // fixed tests
    foreach (ref test; prev.failedClangTests.keys) {
      if (test !in testFile.failedClangTests)
        testFile.fixed ~= Test(test, false);
    }
    foreach (ref test; prev.failedLibcxxTests.keys) {
      if (test !in testFile.failedLibcxxTests)
        testFile.fixed ~= Test(test, true);
    }

    testFile.failedTestsDiff = cast(int)testFile.numFailedTests() - cast(int)prev.numFailedTests();
    ++fileIndex;
  }

  string getTestOutput(ref Test test, ref TestFileData testFile) {
    /* stderr.writeln("test output: ", testFile.name); */
    /* stderr.writeln("Checking for ", test.file); */

    auto lines = File(testFile.name).byLineCopy.array();
    string result;
    /* stderr.writeln(lines); */

    for(size_t i = 0; i != lines.length; ++i) {
      string line = lines[i];
      void advance() { ++i; line = lines[i]; }
      if (line.startsWith("FAIL:")) {
        size_t colonColonIndex = line.indexOf(":: ");
        if (colonColonIndex == cast(size_t)-1)
          continue;

        auto testName = line[colonColonIndex + 3..line.indexOf(' ', colonColonIndex + 3)];
        if (testName != test.file) {
          continue;
        }
        // Fine the next line that's just "--", that's where the output starts.
        while (line != "--")
          advance();

        // Skip the start line.
        advance();
        // The next -- line is the end of the output.
        while (line != "--" && line != "") {
          result ~= line ~ "\n";
          advance();
        }
      }

    }
    return result;
  }

  void addSupNotes(ref Test test, ref TestFileData testFile) {
    auto contents = loadFile(test);
    auto testOutput = getTestOutput(test, testFile);

    if (test.file == "std/utilities/variant/variant.get/get_index.pass.cpp") {
      stderr.writeln("############################################################");
      stderr.writeln(testOutput);
    }

    if (contents.indexOf("-fexperimental-new-constant-interpreter") != -1)
      writeln("<sup class='hardfail'>[Explicit Test]</sup>");
    if (contents.indexOf("__builtin_constant_p") != -1 ||
        testOutput.indexOf("_LIBCPP_ASSERT_VALID_INPUT_RANGE") != -1)
      writeln("<sup class='note'>[builtin_constant_p]</sup>");
    if (contents.indexOf("__builtin_bit_cast") != -1)
      writeln("<sup class='note'>[builtin_bit_cast]</sup>");
    if (testOutput.indexOf("PLEASE submit a bug report") != -1)
      writeln("<sup class='hardfail'>[Crash]</sup>");
  }

  // We print the results in reverse order, so the latest one is first in the table.
  foreach_reverse (ref testFile; testFiles.tail(TABLE_LIMIT)) {
    writeln("<tr>");
    writeln("  <td>", dateFromFilename(testFile.name), "</td>");
    writeln("  <td class='num'>", testFile.numFailedTests(), "</td>");
    writeln("  <td class='num'>", testFile.numErrors, "</td>");

    writeln("  <td class='num'>");
    if (&testFile != &testFiles[0]) {
      writeln("<span class='", (testFile.failedTestsDiff < 0 ? "pos" : "neg"), "'>");
      writeln(testFile.failedTestsDiff);
      writeln("</span>");
    }
    writeln("  </td>");

    // Print regressions.
    writeln("<td>");
    if (!testFile.regressions.empty()) {
      writeln("  <ul>");
      foreach (ref Test t; sort(testFile.regressions)) {
        writeln("<li>", t);
        addSupNotes(t, testFile);
        writeln("</li>");
      }
      writeln("</ul>");
    }
    writeln("</td>");

    // Print fixed tests.
    writeln("<td>");
    if (!testFile.fixed.empty()) {
      writeln("  <ul>");
      foreach (ref Test t; sort(testFile.fixed)) {
        writeln("<li>", t);
        addSupNotes(t, testFile);
        writeln("</li>");
      }
      writeln("</ul>");
    }
    writeln("</td>");


    writeln("</tr>");
  }

  writeln("<tr><td colspan='6'>Showing only ", TABLE_LIMIT, " datasets of ", testFiles.length, " total</td></tr>");
  writeln("</table>");

  writeln("</body>");
  writeln("</html>");
}
