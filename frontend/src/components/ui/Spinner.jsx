const sizes = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-10 w-10" };

export default function Spinner({ size = "md" }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${sizes[size]}`}
    />
  );
}
