FROM node:20-alpine
WORKDIR /app
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY packages ./packages
COPY apps/artifice-draft ./apps/artifice-draft
RUN npm install -g pnpm && pnpm install --filter artifice-draft...
CMD ["pnpm", "--filter", "artifice-draft", "dev"]
