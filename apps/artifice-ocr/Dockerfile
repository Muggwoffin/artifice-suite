FROM node:20-alpine
WORKDIR /app
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY packages ./packages
COPY apps/artifice-ocr ./apps/artifice-ocr
RUN npm install -g pnpm && pnpm install --filter artifice-ocr...
CMD ["pnpm", "--filter", "artifice-ocr", "dev"]
