// Mock VS Code API for testing
export const workspace = {
    workspaceFolders: [],
    getConfiguration: () => ({
        get: () => ''
    }),
    asRelativePath: (path: string) => path
};

export const window = {
    showErrorMessage: () => {},
    showWarningMessage: () => {},
    showInformationMessage: () => {},
    withProgress: async (options: any, task: Function) => task({ report: () => {} }),
    activeTextEditor: undefined
};

export const commands = {
    registerCommand: () => ({ dispose: () => {} })
};

export const  Uri = {
    file: (path: string) => ({ fsPath: path }),
    parse: (uri: string) => ({ fsPath: uri })
};

export const ProgressLocation = {
    Notification: 15
};

export const ViewColumn = {
    One: 1
};
