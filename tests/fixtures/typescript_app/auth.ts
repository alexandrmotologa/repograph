import { Account, UserCredentials } from "./account";

export function authenticateUser(creds: UserCredentials): boolean {
  const acc = new Account("USR-1");
  return acc.validate(creds);
}
