import { Container } from "@/components/ui/container";

export default function Home() {
  return (
    <Container className="py-16">
      <h1 className="font-mono text-2xl font-semibold text-primary">{{PROJECT_NAME}}</h1>
      <p className="mt-2 text-muted-foreground">App shell.</p>
    </Container>
  );
}
