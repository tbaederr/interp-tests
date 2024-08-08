import std.stdio;
import std.algorithm;
import std.array;
import std.string;
import std.range;
import std.file;
import std.conv : to;


immutable int TABLE_LIMIT = 5;
immutable string CLANG_TEST_BASE_DIR = "/home/tbaeder/code/llvm-project/clang/test/";


struct TestFileData  {
  string name;
  bool[string] failedTests;
  string[] regressions;
  string[] fixed;
  int failedTestsDiff; // diff to previous date.
}

string dateFromFilename(string filename) {
  filename = filename[filename.indexOf('/') + 1..$];
  filename = filename[0..filename.lastIndexOf('.')];
  return filename;
}

string loadFile(string filename) {
  try {
    return readText(CLANG_TEST_BASE_DIR ~ filename);
  } catch(Throwable) {
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
    <td class='slim'><em>CodeGenObjC/encode-test-4.m</em></td>
    <td class='slim'>Comparison against @encode is unspecified.</td>
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
      data: [ALL_DATA],
      stepped: true,
      backgroundColor: '#7ED7C1',
      borderColor: 'green',
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
        tf.failedTests[name] = true;
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
  string data;
  foreach (ref t; testFiles) {
    data ~= to!string(t.failedTests.length) ~ ", ";
  }


  writeln(preamble.replace("ALL_LABELS", labels).replace("ALL_DATA", data));


  writeln(
      "<table class='failuretable'>
        <tr>
          <th>Date</th>
          <th>Failures</th>
          <th>Diff</th>
          <th>Regressions</th>
          <th>Fixed</th>
        </tr>
        ");

  // Compute regressions.

  size_t fileIndex = 1;
  foreach (ref testFile; testFiles.drop(1)) {
    const TestFileData* prev = &testFiles[fileIndex - 1];

    foreach (ref test; testFile.failedTests.keys) {
      if (test !in prev.failedTests)
        testFile.regressions ~= test;
    }

    // fixed tests
    foreach (ref test; prev.failedTests.keys) {
      if (test !in testFile.failedTests)
        testFile.fixed ~= test;
    }

    testFile.failedTestsDiff = cast(int)testFile.failedTests.length - cast(int)prev.failedTests.length;
    ++fileIndex;
  }


  void addSupNotes(string filename) {
    auto contents = loadFile(filename);

    if (contents.indexOf("-fexperimental-new-constant-interpreter") != -1)
      writeln("<sup class='hardfail'>[Explicit Test]</sup>");
    if (contents.indexOf("__builtin_constant_p") != -1)
      writeln("<sup class='note'>[builtin_constant_p]</sup>");
    if (contents.indexOf("__builtin_bit_cast") != -1)
      writeln("<sup class='note'>[builtin_bit_cast]</sup>");
  }

  // We print the results in reverse order, so the latest one is first in the table.
  foreach_reverse (ref testFile; testFiles.tail(TABLE_LIMIT)) {
    writeln("<tr>");
    writeln("  <td>", dateFromFilename(testFile.name), "</td>");
    writeln("  <td class='num'>", testFile.failedTests.length, "</td>");


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
      foreach (string t; sort(testFile.regressions)) {
        auto contents = loadFile(t);
        writeln("<li>", t);
        addSupNotes(t);
        writeln("</li>");
      }
      writeln("</ul>");
    }
    writeln("</td>");

    // Print fixed tests.
    writeln("<td>");
    if (!testFile.fixed.empty()) {
      writeln("  <ul>");
      foreach (string t; sort(testFile.fixed)) {
        auto contents = loadFile(t);
        writeln("<li>", t);
        addSupNotes(t);
        writeln("</li>");
      }
      writeln("</ul>");
    }
    writeln("</td>");


    writeln("</tr>");
  }

  writeln("<tr><td colspan='5'>Showing only ", TABLE_LIMIT, " datasets of ", testFiles.length, " total</td></tr>");
  writeln("</table>");

  writeln("</body>");
  writeln("</html>");
}
