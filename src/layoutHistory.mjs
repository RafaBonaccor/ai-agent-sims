function cloneLayout(layout) {
  return JSON.parse(JSON.stringify(layout ?? {}));
}

function layoutSignature(layout) {
  return JSON.stringify(layout ?? {});
}

export class LayoutHistory {
  constructor(limit = 40) {
    this.limit = Math.max(1, Number(limit) || 40);
    this.undoStack = [];
    this.redoStack = [];
  }

  record(before, after) {
    if (!before || layoutSignature(before) === layoutSignature(after)) {
      return false;
    }
    this.undoStack.push(cloneLayout(before));
    if (this.undoStack.length > this.limit) {
      this.undoStack.splice(0, this.undoStack.length - this.limit);
    }
    this.redoStack.length = 0;
    return true;
  }

  undo(current) {
    if (!this.undoStack.length) return null;
    this.redoStack.push(cloneLayout(current));
    return this.undoStack.pop();
  }

  redo(current) {
    if (!this.redoStack.length) return null;
    this.undoStack.push(cloneLayout(current));
    return this.redoStack.pop();
  }

  get canUndo() {
    return this.undoStack.length > 0;
  }

  get canRedo() {
    return this.redoStack.length > 0;
  }
}
