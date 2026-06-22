/** Reactive command history — module-level $state. */

let _entries = $state([]);
let _index = $state(-1);

export const history = {
  /** @returns {string[]} */
  get entries() {
    return _entries;
  },

  /** @returns {number} */
  get index() {
    return _index;
  },

  /** Add a command to history. */
  push(cmd) {
    if (!cmd.trim()) return;
    _entries = [cmd, ..._entries].slice(0, 100);
    _index = -1;
  },

  /** Navigate back in history. Returns the command string. */
  back() {
    if (_entries.length === 0) return "";
    _index = Math.min(_entries.length - 1, _index + 1);
    return _entries[_index];
  },

  /** Navigate forward in history. Returns the command string. */
  forward() {
    if (_index <= 0) {
      _index = -1;
      return "";
    }
    _index -= 1;
    return _entries[_index];
  },

  /** Reset navigation index. */
  reset() {
    _index = -1;
  },
};
