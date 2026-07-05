import { useState } from 'react';
import { Box, Button, Heading, Text, VStack, Spinner, Code } from '@chakra-ui/react';

function App() {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [cycleData, setCycleData] = useState<any | null>(null);

  const handleGenerateCycle = async () => {
    setLoading(true);
    setError(null);
    setCycleData(null);

    try {
      // Replace with your exact FastAPI route and pass any required payloads
      const response = await fetch('http://localhost:8000/api/generate/wendler', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        // Example fallback payload; adjust to match your backend Pydantic schema
        body: JSON.stringify({
          squat_1rm: 315,
          bench_1rm: 225,
          deadlift_1rm: 405,
          press_1rm: 135,
        }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.statusText}`);
      }

      const data = await response.json();
      setCycleData(data);
    } catch (err: any) {
      setError(err.message || 'Something went wrong communicating with the API.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box p={8} maxW="container.md" mx="auto">
      <VStack gap={6} align="flex-start">
        <Heading size="2xl">Macrocycle Generator</Heading>
        <Text fontSize="lg" color="gray.500">
          Generate structured multi-week training blocks directly into your tracking hierarchy.
        </Text>

        <Button 
          colorPalette="blue" 
          size="lg" 
          disabled={loading}
          onClick={handleGenerateCycle}
        >
          {loading ? <Spinner size="sm" mr={2} /> : null}
          {loading ? 'Generating...' : 'Generate 5/3/1 Cycle'}
        </Button>

        {/* Error Feedback */}
        {error && (
          <Box p={4} bg="red.50" color="red.700" borderRadius="md" w="full">
            <Text fontWeight="bold">Error Generation Failed:</Text>
            <Text>{error}</Text>
          </Box>
        )}

        {/* Success / Data Output View */}
        {cycleData && (
          <VStack gap={4} align="flex-start" w="full">
            <Box p={4} bg="green.50" color="green.700" borderRadius="md" w="full">
              <Text fontWeight="bold">Success!</Text>
              <Text>Macrocycle created and stored successfully.</Text>
            </Box>
            
            <Text fontWeight="bold" mt={2}>Returned Payload Summary:</Text>
            <Code p={4} borderRadius="md" w="full" overflowX="auto">
              {JSON.stringify(cycleData, null, 2)}
            </Code>
          </VStack>
        )}
      </VStack>
    </Box>
  );
}

export default App;