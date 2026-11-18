// Decode a SudokuPad puzzle link with SudokuPad's own PuzzleLoader, in plain Node.
//
//   echo -n "<fpuz…|ctc…|scl…>" | node sudokupad_loader.js <hosts-json> <har-file>   prints the puzzle as JSON
//
// `PuzzleLoader.parsePuzzleData(id)` is SudokuPad's own conversion of an encoded body (`scl`, `ctc`, `fpuz`,
// `fpuzzles`) into puzzle JSON. The app files come from a recording of the app (a HAR file that sudokupad-art's
// `render_real.js --record` writes), never from this
// repo, because SudokuPad is not open source. `<hosts-json>` is the JSON list of the app's hostnames, whose
// entries the recording is searched for; `<har-file>` is the recording's path, which sudokupad_codec.default_har
// chooses, so the default path lives in that one place.
//
// Exit 1 and a message on stderr when the body does not parse (`parsePuzzleData` hands the input string back on
// a parse error instead of throwing, so a string result is that failure); exit 2 when the recording is missing,
// holds no loader or holds code that does not load, which is the environment, not the link.
const crypto = require('crypto');
const fs = require('fs');
const vm = require('vm');

// puzpatcher.bundle.js defines `loadFPuzzle` (the f-puzzles converter) and `PuzzleZipper` (the compact-format
// unzipper) that puzzleloader.js destructures at load.
const APP_FILES = ['puzpatcher.bundle.js', 'puzzleloader.js'];

function requireHar(file) {
  if (!fs.existsSync(file)) throw new Error(`no recording of SudokuPad's app at ${file}: record one first with sudokupad-art's render_real.js --record`);
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

// The body of the newest recorded GET from the app's hosts for `/<name>`: a re-record is merged in after the
// entries it refreshes, so the last one is the newest.
function recordedFile(har, hosts, name) {
  const e = har.log.entries.filter(e => e.request.method === 'GET' && hosts.includes(new URL(e.request.url).hostname)
    && e.response.content.text && new URL(e.request.url).pathname === `/${name}`).pop();
  return e && (e.response.content.encoding === 'base64' ? Buffer.from(e.response.content.text, 'base64').toString() : e.response.content.text);
}

// Anything that goes wrong here is the recording or the environment, never the link.
function loadApp(har, hosts) {
  const logs = [], sink = (...args) => logs.push(args.map(String).join(' '));
  // The app's code reaches for `md5Digest` (a page global defined outside the loader) to name an f-puzzles
  // puzzle; Node's md5 stands in. No fetch, window or document is given: the loader needs none to parse.
  const context = vm.createContext({
    console: { log: sink, info: sink, warn: sink, error: sink, time() {}, timeEnd() {} },
    setTimeout, clearTimeout, md5Digest: s => crypto.createHash('md5').update(s).digest('hex'),
  });
  for (const name of APP_FILES) {
    const source = recordedFile(har, hosts, name);
    if (!source) throw new Error(`the recording holds no ${name}: re-record it`);
    try { vm.runInContext(source, context, { filename: name }); }
    catch (e) { throw new Error(`the recorded ${name} does not load in plain Node (${e.message}): SudokuPad may have changed it`); }
  }
  return { loader: vm.runInContext('PuzzleLoader', context), logs };
}

async function parseLink(encoded, { loader, logs }) {
  const puzzle = await loader.parsePuzzleData(encoded);
  if (typeof puzzle === 'string') throw new Error(`SudokuPad's PuzzleLoader could not parse it${logs.length ? ': ' + logs.join(' ') : ''}`);
  return JSON.parse(JSON.stringify(puzzle));      // out of the vm context: plain objects
}

async function main() {
  let app;
  try { app = loadApp(requireHar(process.argv[3]), JSON.parse(process.argv[2])); }
  catch (e) { console.error(e.message); process.exit(2); }
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  try { process.stdout.write(JSON.stringify(await parseLink(input.trim(), app))); }
  catch (e) { console.error(e.message); process.exit(1); }
}

main();
