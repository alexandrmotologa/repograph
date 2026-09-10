export interface UserCredentials {
  username: string;
  token: string;
}

export class Account {
  private id: string;

  constructor(id: string) {
    this.id = id;
  }

  public validate(credentials: UserCredentials): boolean {
    return credentials.token.length > 0;
  }
}
