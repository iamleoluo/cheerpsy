import "next-auth";

declare module "next-auth" {
  interface User {
    role?: string;
    accessToken?: string;
  }

  interface Session {
    user: User & {
      id?: string;
      role?: string;
      accessToken?: string;
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: string;
    accessToken?: string;
  }
}
