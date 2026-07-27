FROM node:20-alpine
WORKDIR /app
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY packages ./packages
COPY apps/artifice-graph ./apps/artifice-graph
RUN npm install -g pnpm && pnpm install --filter artifice-graph...
CMD ["pnpm", "--filter", "artifice-graph", "dev"]
