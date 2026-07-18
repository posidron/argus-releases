import {
  constants,
  createCipheriv,
  createDecipheriv,
  createHash,
  privateDecrypt,
  publicEncrypt,
  randomBytes,
} from "node:crypto";
import {
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import path from "node:path";

const MAGIC = Buffer.from("ARGUSENC2");

function parseArgs(argv) {
  const [mode, ...rest] = argv;
  const options = new Map();
  for (let index = 0; index < rest.length; index += 2) {
    const key = rest[index];
    const value = rest[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error("Arguments must be provided as --name value pairs.");
    }
    options.set(key.slice(2), value);
  }
  return { mode, options };
}

function required(options, name) {
  const environmentNames = {
    input: "ARGUS_INPUT",
    label: "ARGUS_LABEL",
    output: "ARGUS_OUTPUT",
    "private-key": "ARGUS_ARTIFACT_PRIVATE_KEY",
    "public-key": "ARGUS_PUBLIC_KEY_PATH",
    root: "ARGUS_SOURCE_ROOT",
    target: "ARGUS_TARGET",
    version: "ARGUS_VERSION",
  };
  const value = options.get(name) ?? process.env[environmentNames[name]];
  if (!value) throw new Error(`Missing --${name}.`);
  return value;
}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

function encrypt(content, publicKey) {
  const dataKey = randomBytes(32);
  const wrappedKey = publicEncrypt(
    {
      key: publicKey,
      oaepHash: "sha256",
      padding: constants.RSA_PKCS1_OAEP_PADDING,
    },
    dataKey,
  );
  if (wrappedKey.length > 65535) {
    throw new Error("Wrapped artifact key is unexpectedly large.");
  }
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", dataKey, nonce);
  const ciphertext = Buffer.concat([cipher.update(content), cipher.final()]);
  const keyLength = Buffer.alloc(2);
  keyLength.writeUInt16BE(wrappedKey.length);
  return Buffer.concat([
    MAGIC,
    keyLength,
    wrappedKey,
    nonce,
    cipher.getAuthTag(),
    ciphertext,
  ]);
}

function decrypt(content, privateKey) {
  if (!content.subarray(0, MAGIC.length).equals(MAGIC)) {
    throw new Error("Encrypted artifact has an invalid header.");
  }
  const keyLengthStart = MAGIC.length;
  const keyStart = keyLengthStart + 2;
  const keyLength = content.readUInt16BE(keyLengthStart);
  const nonceStart = keyStart + keyLength;
  const tagStart = nonceStart + 12;
  const dataStart = tagStart + 16;
  const dataKey = privateDecrypt(
    {
      key: privateKey,
      oaepHash: "sha256",
      padding: constants.RSA_PKCS1_OAEP_PADDING,
    },
    content.subarray(keyStart, nonceStart),
  );
  const decipher = createDecipheriv(
    "aes-256-gcm",
    dataKey,
    content.subarray(nonceStart, tagStart),
  );
  decipher.setAuthTag(content.subarray(tagStart, dataStart));
  return Buffer.concat([
    decipher.update(content.subarray(dataStart)),
    decipher.final(),
  ]);
}

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(fullPath)));
    if (entry.isFile()) files.push(fullPath);
  }
  return files;
}

async function selectBundles(root, target) {
  const bundleRoot = path.join(
    root,
    "app",
    "src-tauri",
    "target",
    target,
    "release",
    "bundle",
  );
  const files = await walk(bundleRoot);
  if (target.endsWith("apple-darwin")) {
    const matches = files.filter(
      (file) => file.endsWith(".dmg") && file.includes(`${path.sep}dmg${path.sep}`),
    );
    if (matches.length !== 1) {
      throw new Error(`Expected one DMG, found ${matches.length}.`);
    }
    return [{ source: matches[0], suffix: ".dmg" }];
  }
  const installers = files.filter(
    (file) => file.endsWith(".exe") && file.includes(`${path.sep}nsis${path.sep}`),
  );
  const packages = files.filter(
    (file) => file.endsWith(".msi") && file.includes(`${path.sep}msi${path.sep}`),
  );
  if (installers.length !== 1 || packages.length !== 1) {
    throw new Error(
      `Expected one NSIS executable and one MSI, found ${installers.length}/${packages.length}.`,
    );
  }
  return [
    { source: installers[0], suffix: "-setup.exe" },
    { source: packages[0], suffix: ".msi" },
  ];
}

async function pack(options) {
  const root = path.resolve(required(options, "root"));
  const target = required(options, "target");
  const version = required(options, "version");
  const label = required(options, "label");
  const output = path.resolve(required(options, "output"));
  const publicKey = await readFile(path.resolve(required(options, "public-key")), "utf8");
  const bundles = await selectBundles(root, target);
  await rm(output, { recursive: true, force: true });
  await mkdir(output, { recursive: true });

  const files = [];
  for (const bundle of bundles) {
    const name = `ARGUS_${version}_${label}${bundle.suffix}`;
    const content = await readFile(bundle.source);
    const encryptedName = `${name}.enc`;
    await writeFile(path.join(output, encryptedName), encrypt(content, publicKey), {
      mode: 0o600,
    });
    files.push({
      name,
      encryptedName,
      sha256: sha256(content),
      size: content.length,
    });
  }
  await writeFile(
    path.join(output, `${label}.manifest.json.enc`),
    encrypt(
      Buffer.from(JSON.stringify({ version, target, label, files }), "utf8"),
      publicKey,
    ),
    { mode: 0o600 },
  );
  console.log(`Encrypted ${files.length} ${label} release asset(s).`);
}

async function unpack(options) {
  const input = path.resolve(required(options, "input"));
  const output = path.resolve(required(options, "output"));
  const version = required(options, "version");
  const privateKey = required(options, "private-key");
  const allFiles = await walk(input);
  const manifestPaths = allFiles.filter((file) =>
    file.endsWith(".manifest.json.enc"),
  );
  if (manifestPaths.length !== 3) {
    throw new Error(`Expected three platform manifests, found ${manifestPaths.length}.`);
  }
  await rm(output, { recursive: true, force: true });
  await mkdir(output, { recursive: true });

  const expectedNames = new Set([
    `ARGUS_${version}_macOS_arm64.dmg`,
    `ARGUS_${version}_macOS_x64.dmg`,
    `ARGUS_${version}_Windows_x64-setup.exe`,
    `ARGUS_${version}_Windows_x64.msi`,
  ]);
  const emitted = new Set();
  for (const manifestPath of manifestPaths) {
    const manifest = JSON.parse(
      decrypt(await readFile(manifestPath), privateKey).toString("utf8"),
    );
    if (manifest.version !== version || !Array.isArray(manifest.files)) {
      throw new Error("Encrypted artifact manifest has invalid release metadata.");
    }
    for (const entry of manifest.files) {
      if (!expectedNames.has(entry.name) || emitted.has(entry.name)) {
        throw new Error(`Unexpected or duplicate release asset ${entry.name}.`);
      }
      const encryptedMatches = allFiles.filter(
        (file) => path.basename(file) === entry.encryptedName,
      );
      if (encryptedMatches.length !== 1) {
        throw new Error(`Expected one encrypted payload for ${entry.name}.`);
      }
      const content = decrypt(await readFile(encryptedMatches[0]), privateKey);
      if (content.length !== entry.size || sha256(content) !== entry.sha256) {
        throw new Error(`Integrity validation failed for ${entry.name}.`);
      }
      await writeFile(path.join(output, entry.name), content, { mode: 0o600 });
      emitted.add(entry.name);
    }
  }
  if (
    emitted.size !== expectedNames.size ||
    [...expectedNames].some((name) => !emitted.has(name))
  ) {
    throw new Error("The decrypted installer set is incomplete.");
  }
  console.log("Decrypted and verified the exact four-file installer set.");
}

async function encryptLogs(options) {
  const input = path.resolve(required(options, "input"));
  const output = path.resolve(required(options, "output"));
  const label = required(options, "label");
  const publicKey = await readFile(path.resolve(required(options, "public-key")), "utf8");
  await rm(output, { recursive: true, force: true });
  await mkdir(output, { recursive: true });
  let files = [];
  try {
    files = await walk(input);
  } catch (error) {
    if (error?.code === "ENOENT") return;
    throw error;
  }
  for (let index = 0; index < files.length; index += 1) {
    const content = await readFile(files[index]);
    await writeFile(
      path.join(output, `${label}-${index + 1}.log.enc`),
      encrypt(content, publicKey),
      { mode: 0o600 },
    );
  }
  console.log(`Encrypted ${files.length} private build log(s).`);
}

const { mode, options } = parseArgs(process.argv.slice(2));
if (mode === "pack") await pack(options);
else if (mode === "unpack") await unpack(options);
else if (mode === "encrypt-logs") await encryptLogs(options);
else throw new Error(`Unknown mode ${mode}.`);
